"""
Bridge between the web frontend (web/app.js) and the existing Python engine.
Every method here is callable from JS as `pywebview.api.method_name(...)` and
returns a Promise. Nothing about how installs/downloads/accounts actually work
changed - core/ is untouched; this just exposes it over pywebview's JS bridge
instead of wiring it into CustomTkinter widgets.

Long-running work (installs, downloads) is still handed to the existing
TaskManager and runs in the background; a dedicated dispatcher thread here
drains its queue and pushes updates into the page via evaluate_js, mirroring
the desktop app's "poll from one thread only" pattern - progress is throttled
inside core/launcher.py and core/modrinth.py already, so this doesn't flood
the page with events either.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time

import webview

from core import launcher as mc
from core import modrinth as mr
from core import skins as sk
from core import winchrome
from core.auth import AccountStore, MicrosoftDeviceCodeFlow
from core.instances import InstanceManager
from core.settings import Settings
from core.tasks import TaskManager


def _instance_to_dict(inst) -> dict:
    return {
        "id": inst.id,
        "name": inst.name,
        "mc_version": inst.mc_version,
        "loader": inst.loader,
        "loader_version": inst.loader_version,
        "installed": inst.installed,
        "installed_version_id": inst.installed_version_id,
    }


def _account_to_dict(acc, active: bool) -> dict:
    return {"kind": acc.kind, "username": acc.username, "uuid": acc.uuid, "active": active}


def _task_to_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "kind": task.kind,
        "ref_id": task.ref_id,
        "status": task.status,
        "progress": task.progress,
        "detail": task.detail,
        "error": task.error,
    }


class Api:
    def __init__(self):
        self.im = InstanceManager()
        self.accounts = AccountStore(os.path.join(self.im.base_dir, "accounts.json"))
        self.settings = Settings(self.im.base_dir)
        self.tasks = TaskManager()
        self._ms_flow: MicrosoftDeviceCodeFlow | None = None
        self._window = None  # set by main.py right after the window is created

        threading.Thread(target=self._dispatch_loop, daemon=True).start()
        threading.Thread(target=self._token_refresh_loop, daemon=True).start()

    # ------------------------------------------------------------- push loop
    def _dispatch_loop(self):
        """Runs on its own dedicated thread, forever - the only thread allowed
        to call evaluate_js, so pushes never race each other."""
        while True:
            time.sleep(0.08)
            if self._window is None:
                continue
            for task in self.tasks.drain():
                self._push("onTaskEvent", _task_to_dict(task))

    def _token_refresh_loop(self):
        """Keeps the signed-in Microsoft account's session alive in the
        background for as long as the launcher is open - not just right
        before Play. Without this, an account left signed in while you just
        browse Content/Skins/Manage for a while (or leave the launcher open
        overnight) would silently start presenting an expired token to
        anything that isn't the Play button, which looks exactly like being
        logged out even though the underlying refresh token is still fine."""
        while True:
            try:
                if 0 <= self.accounts.active_index < len(self.accounts.accounts):
                    self.accounts.refresh_if_needed(self.accounts.active_index, self.settings.azure_client_id)
            except Exception:
                pass
            time.sleep(5 * 60)

    def _push(self, js_fn: str, *args):
        if not self._window:
            return
        try:
            payload = ", ".join(json.dumps(a) for a in args)
            self._window.evaluate_js(f"window.{js_fn} && window.{js_fn}({payload})")
        except Exception:
            pass

    # ------------------------------------------------------------- instances
    def list_instances(self):
        return [_instance_to_dict(i) for i in self.im.instances]

    def loader_labels(self):
        return mc.LOADER_LABELS

    def loaders(self):
        return mc.LOADERS

    def version_list(self, include_snapshots=True, include_old=False):
        try:
            return {"versions": [v["id"] for v in mc.get_version_list(include_snapshots, include_old)]}
        except Exception as e:
            return {"error": str(e)}

    def loader_mc_versions(self, loader_id, stable_only=False):
        try:
            return {"versions": mc.get_loader_minecraft_versions(loader_id, stable_only)}
        except Exception as e:
            return {"error": str(e)}

    def loader_versions(self, loader_id, mc_version, stable_only=False):
        try:
            return {"versions": mc.get_loader_versions(loader_id, mc_version, stable_only)}
        except Exception as e:
            return {"error": str(e)}

    def create_instance(self, name, mc_version, loader_id, loader_version=None):
        inst = self.im.create(name, mc_version, loader_id, loader_version)
        return _instance_to_dict(inst)

    def delete_instance(self, instance_id):
        self.im.delete(instance_id, delete_files=True)
        return {"ok": True}

    def open_folder(self, instance_id):
        path = self.im.instance_dir(instance_id)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def start_install(self, instance_id):
        inst = self.im.get(instance_id)
        if not inst:
            return {"error": "Instance not found."}

        def work(update):
            def progress_cb(status, current, maximum):
                if maximum:
                    update(min(1.0, current / maximum), status or "Installing...")
                else:
                    update(None, status or "Installing...")

            if self.im.shared_install_lock.locked():
                update(None, "Waiting for another install to finish...")
            with self.im.shared_install_lock:
                update(0, "Preparing...")
                installed_id = mc.install_version(
                    self.im.shared_dir, inst.mc_version, inst.loader, inst.loader_version,
                    progress_cb=progress_cb,
                )
            self.im.mark_installed(inst.id, installed_id)
            update(1.0, "Installed")

        task_id = self.tasks.start(f"Install {inst.name}", work, kind="install_instance", ref_id=inst.id)
        return {"task_id": task_id}

    def play(self, instance_id):
        inst = self.im.get(instance_id)
        if not inst:
            return {"error": "Instance not found."}
        if self.accounts.active_index >= 0:
            # Minecraft/Xbox access tokens expire (~24h) - without this, a
            # long-lived launcher session keeps launching with an
            # increasingly stale token, which shows up as skins failing to
            # load and servers refusing the join, previously fixed only by
            # a full manual re-login. Refreshing before every launch keeps
            # the token valid without ever needing that.
            self.accounts.refresh_if_needed(self.accounts.active_index, self.settings.azure_client_id, force=True)
        account = self.accounts.get_active()
        if not account:
            return {"error": "no_account"}

        needs_install = not inst.installed or not mc.is_version_installed(
            inst.installed_version_id or inst.mc_version, self.im.shared_dir
        )

        def work(update):
            if needs_install:
                update(0, "Installing...")

                def progress_cb(status, current, maximum):
                    if maximum:
                        update(min(1.0, current / maximum), status or "Installing...")
                    else:
                        update(None, status or "Installing...")

                if self.im.shared_install_lock.locked():
                    update(None, "Waiting for another install to finish...")
                with self.im.shared_install_lock:
                    installed_id = mc.install_version(
                        self.im.shared_dir, inst.mc_version, inst.loader, inst.loader_version,
                        progress_cb=progress_cb,
                    )
                self.im.mark_installed(inst.id, installed_id)
            else:
                installed_id = inst.installed_version_id

            update(None, "Starting Minecraft...")
            self._sync_shared_files_in(self.im.instance_dir(inst.id))
            options = mc.build_options(
                username=account.username,
                uuid_=account.uuid,
                token=account.access_token,
                ram_min_mb=self.settings.ram_min_mb,
                ram_max_mb=self.settings.ram_max_mb,
                extra_jvm_args=inst.jvm_args.split() if inst.jvm_args else None,
                game_directory=self.im.instance_dir(inst.id),
            )
            proc = mc.launch(installed_id, self.im.shared_dir, options)
            update(1.0, "Running")
            self._watch_process(inst.id, proc)

        task_id = self.tasks.start(f"Launch {inst.name}", work, kind="launch", ref_id=inst.id)
        return {"task_id": task_id}

    def _watch_process(self, instance_id, proc):
        """Streams game stdout to the web console panel and reports when the game
        exits, so the panel can close itself - same behavior as the desktop
        ConsoleWindow. Output is batched (~10x/second) instead of pushed line by
        line, which would otherwise flood evaluate_js for a chatty game log."""

        def pump():
            buffer = []
            last_flush = time.monotonic()

            def flush(force=False):
                nonlocal buffer, last_flush
                now = time.monotonic()
                if buffer and (force or now - last_flush >= 0.1):
                    text = "".join(buffer)
                    buffer = []
                    last_flush = now
                    self._push("onGameOutput", instance_id, text)

            try:
                for line in proc.stdout:
                    buffer.append(line)
                    flush()
            except Exception:
                pass
            flush(force=True)

            exit_code = None
            try:
                exit_code = proc.wait(timeout=5)
            except Exception:
                pass
            self._sync_shared_files_out(self.im.instance_dir(instance_id))
            self._push("onGameExit", instance_id, exit_code)

        threading.Thread(target=pump, daemon=True).start()

    # Minecraft has no native concept of "shared settings across instances" -
    # it always treats one game directory as the single source for saves,
    # mods, config, options.txt, and servers.dat together. Since mods/saves
    # genuinely need to stay per-instance, video settings and the multiplayer
    # server list are copied in before launch and copied back to shared/ after
    # the game exits - so changing either from any instance carries over to
    # every other instance, without needing symlinks (which need admin/dev-mode
    # privileges on Windows and would be a portability headache).
    _SHARED_SYNC_FILES = ("options.txt", "servers.dat")

    def _sync_shared_files_in(self, instance_dir):
        for fname in self._SHARED_SYNC_FILES:
            src = os.path.join(self.im.shared_dir, fname)
            if os.path.exists(src):
                try:
                    shutil.copyfile(src, os.path.join(instance_dir, fname))
                except Exception:
                    pass

    def _sync_shared_files_out(self, instance_dir):
        for fname in self._SHARED_SYNC_FILES:
            src = os.path.join(instance_dir, fname)
            if os.path.exists(src):
                try:
                    os.makedirs(self.im.shared_dir, exist_ok=True)
                    shutil.copyfile(src, os.path.join(self.im.shared_dir, fname))
                except Exception:
                    pass

    # --------------------------------------------------------------- content
    def search_content(self, query, project_type, instance_id=None, offset=0):
        inst = self.im.get(instance_id) if instance_id else None
        loader = inst.loader if inst else None
        game_version = inst.mc_version if inst else None
        try:
            data = mr.search(query, project_type, loader=loader, game_version=game_version, limit=20, offset=offset)
            return {"hits": data.get("hits", []), "total_hits": data.get("total_hits", 0)}
        except Exception as e:
            return {"error": str(e)}

    def get_versions(self, project_id, instance_id, project_type):
        inst = self.im.get(instance_id)
        if not inst:
            return {"error": "Instance not found."}
        try:
            versions = mr.get_project_versions(
                project_id, loader=inst.loader, game_version=inst.mc_version, project_type=project_type,
            )
            if project_type not in ("shader", "resourcepack"):
                versions = mr.filter_compatible_versions(versions, loader=inst.loader, game_version=inst.mc_version)
            return {"versions": versions}
        except Exception as e:
            return {"error": str(e)}

    def get_modpack_versions(self, project_id):
        try:
            return {"versions": mr.get_project_versions(project_id)}
        except Exception as e:
            return {"error": str(e)}

    def install_content(self, instance_id, project_type, version, name=None, icon_url=None):
        inst = self.im.get(instance_id)
        if not inst:
            return {"error": "Instance not found."}

        def work(update):
            project_id = version.get("project_id")
            version_id = version.get("id")

            if project_id and self.im.is_content_installed(inst.id, project_id, version_id):
                update(1.0, "Already installed")
                return

            update(0, "Downloading...")
            dest = mr.install_content(
                self.im.instance_dir(inst.id), project_type, version,
                progress_cb=lambda w, t: update((w / t) if t else None, "Downloading..."),
            )
            if project_id:
                self.im.record_installed_content(
                    inst.id, project_id, version_id, os.path.basename(dest), project_type,
                    name=name, icon_url=icon_url,
                )

            installed_extra = 0
            if project_type in ("mod", "shader"):
                update(None, "Checking dependencies...")
                already_installed = set(self.im.get_installed_content(inst.id).keys())
                deps = mr.resolve_dependencies(
                    version, loader=inst.loader, game_version=inst.mc_version,
                    already_installed=already_installed,
                )
                for i, dep_version in enumerate(deps, start=1):
                    dep_name = dep_version.get("name") or dep_version.get("version_number", "dependency")
                    update(i / max(len(deps), 1), f"Installing dependency: {dep_name}")
                    dep_dest = mr.install_content(self.im.instance_dir(inst.id), "mod", dep_version)
                    installed_extra += 1
                    dep_project_id = dep_version.get("project_id")
                    if dep_project_id:
                        self.im.record_installed_content(
                            inst.id, dep_project_id, dep_version.get("id"), os.path.basename(dep_dest), "mod"
                        )

            label = "Installed" if installed_extra == 0 else f"Installed + {installed_extra} new dependencies"
            update(1.0, label)

        task_id = self.tasks.start(
            f"Install {version.get('name') or version.get('version_number', 'mod')} -> {inst.name}",
            work, kind="install_content", ref_id=inst.id,
        )
        return {"task_id": task_id}

    def list_installed_content(self, instance_id):
        inst = self.im.get(instance_id)
        if not inst:
            return {"error": "Instance not found."}
        items = self.im.list_installed_content(instance_id)
        self._hydrate_content_names(instance_id, items)
        return {"items": items}

    def _hydrate_content_names(self, instance_id, items):
        """Fill in each installed item's display name/icon from Modrinth,
        caching the result into the instance's content manifest so this only
        ever has to hit the network once per mod (dependencies and modpack-
        bundled content don't get a name/icon at install time, so this is
        what backfills those). Anything with no project_id at all - i.e. a
        file the user dropped into the folder by hand rather than installing
        through GLauncher - is left alone, so the Manage tab correctly shows
        just its filename with no icon for those."""
        missing = [i["project_id"] for i in items if i.get("project_id") and not i.get("name")]
        if not missing:
            return
        try:
            projects = mr.get_projects(missing)
        except Exception:
            return
        by_id = {p["id"]: p for p in projects if p.get("id")}
        for item in items:
            proj = by_id.get(item.get("project_id"))
            if not proj:
                continue
            item["name"] = proj.get("title") or item.get("filename")
            item["icon_url"] = proj.get("icon_url") or ""
            self.im.record_installed_content(
                instance_id, item["project_id"], item.get("version_id"),
                item.get("filename"), item.get("project_type"),
                name=item["name"], icon_url=item["icon_url"],
            )

    def delete_installed_content(self, instance_id, project_id):
        inst = self.im.get(instance_id)
        if not inst:
            return {"error": "Instance not found."}
        return self.im.delete_installed_content(instance_id, project_id)

    def install_modpack(self, title, version):
        def work(update):
            update(0, "Downloading...")
            mrpack_path = mr.install_content(
                self.im.instances_dir, "modpack", version,
                progress_cb=lambda w, t: update((w / t) if t else None, "Downloading..."),
            )

            import minecraft_launcher_lib as mll
            info = mll.mrpack.get_mrpack_information(mrpack_path)
            loader_id, loader_version = mc.detect_mrpack_loader(mrpack_path)

            new_inst = self.im.create(title, info["minecraftVersion"], loader_id, loader_version)
            inst_dir = self.im.instance_dir(new_inst.id)

            update(None, "Installing modpack...")

            def progress_cb(status, current, maximum):
                update((current / maximum) if maximum else None, status or "Installing modpack...")

            if self.im.shared_install_lock.locked():
                update(None, "Waiting for another install to finish...")
            with self.im.shared_install_lock:
                installed_id = mc.install_modpack(
                    mrpack_path, self.im.shared_dir, modpack_directory=inst_dir, progress_cb=progress_cb,
                )
            self.im.mark_installed(new_inst.id, installed_id)

            # Identify every mod/resourcepack/shader the pack actually put on
            # disk by content hash and register it as already-installed for
            # this instance - otherwise none of that shows up in Manage, and
            # searching for one of those mods later would offer to "install"
            # something that's already sitting there. Hash-based means this
            # catches content bundled as raw files in the pack's overrides/
            # folder just as reliably as ones tracked in its index.json.
            update(None, "Identifying bundled content...")
            for entry in mr.identify_installed_files(inst_dir):
                self.im.record_installed_content(
                    new_inst.id, entry["project_id"], entry["version_id"],
                    entry["filename"], entry["project_type"],
                )

            update(1.0, f"Installed as new instance '{title}'")

        task_id = self.tasks.start(f"Install modpack {title}", work, kind="install_modpack")
        return {"task_id": task_id}

    # -------------------------------------------------------------- accounts
    def list_accounts(self):
        return [_account_to_dict(a, i == self.accounts.active_index) for i, a in enumerate(self.accounts.accounts)]

    def add_offline_account(self, username):
        self.accounts.add_offline(username)
        return self.list_accounts()

    def set_active_account(self, index):
        self.accounts.set_active(index)
        return self.list_accounts()

    def remove_account(self, index):
        self.accounts.remove(index)
        return self.list_accounts()

    def get_azure_client_id(self):
        return self.settings.azure_client_id or ""

    def ms_request_code(self, client_id):
        self._ms_flow = MicrosoftDeviceCodeFlow(client_id)
        try:
            data = self._ms_flow.request_code()
            self._ms_flow.open_browser(data.get("verification_uri", "https://microsoft.com/link"))
            return data
        except Exception as e:
            return {"error": str(e)}

    def ms_wait_and_complete(self, expires_in=900):
        if not self._ms_flow:
            return {"error": "No sign-in in progress."}
        try:
            token_data = self._ms_flow.poll_for_token(expires_in=expires_in)
            login_data = self._ms_flow.complete(token_data)
            self.accounts.add_microsoft(login_data)
            return {"accounts": self.list_accounts()}
        except Exception as e:
            return {"error": str(e)}

    # ----------------------------------------------------------------- skins
    def _active_ms_account(self):
        acc = self.accounts.get_active()
        if not acc:
            return None, {"error": "No account selected."}
        if acc.kind != "microsoft":
            return None, {"error": "Skins and capes require a signed-in Microsoft account (offline accounts always show the default Steve/Alex model - that's normal, not a bug)."}
        return acc, None

    def get_skin_profile(self):
        acc, err = self._active_ms_account()
        if err:
            return err
        try:
            return sk.get_profile(acc.access_token)
        except Exception as e:
            return {"error": str(e)}

    def get_account_skin_url(self, index):
        """Returns the real skin texture URL for the given account (by index into
        list_accounts()), or None for offline accounts / on any failure - used to
        render the sidebar account switcher's avatar from the actual current skin."""
        try:
            acc = self.accounts.accounts[index]
        except (IndexError, TypeError):
            return {"url": None}
        if acc.kind != "microsoft":
            return {"url": None}
        try:
            profile = sk.get_profile(acc.access_token)
            skins = profile.get("skins", [])
            active = next((s for s in skins if s.get("state") == "ACTIVE"), skins[0] if skins else None)
            return {"url": active.get("url") if active else None}
        except Exception:
            return {"url": None}

    def pick_skin_file(self):
        """Opens a native file picker for a PNG skin. Returns the chosen path, or None."""
        if not self._window:
            return {"error": "Window not ready."}
        try:
            import webview

            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN, file_types=("PNG Files (*.png)",)
            )
            if not result:
                return {"path": None}
            return {"path": result[0]}
        except Exception as e:
            return {"error": str(e)}

    def upload_skin(self, file_path, variant="classic"):
        acc, err = self._active_ms_account()
        if err:
            return err
        try:
            return sk.upload_skin_file(acc.access_token, file_path, variant)
        except Exception as e:
            return {"error": str(e)}

    def set_skin_url(self, url, variant="classic"):
        acc, err = self._active_ms_account()
        if err:
            return err
        try:
            return sk.set_skin_from_url(acc.access_token, url, variant)
        except Exception as e:
            return {"error": str(e)}

    def reset_skin(self):
        acc, err = self._active_ms_account()
        if err:
            return err
        try:
            return sk.reset_skin(acc.access_token)
        except Exception as e:
            return {"error": str(e)}

    def set_cape(self, cape_id):
        acc, err = self._active_ms_account()
        if err:
            return err
        try:
            return sk.set_active_cape(acc.access_token, cape_id)
        except Exception as e:
            return {"error": str(e)}

    def clear_cape(self):
        acc, err = self._active_ms_account()
        if err:
            return err
        try:
            return sk.clear_active_cape(acc.access_token)
        except Exception as e:
            return {"error": str(e)}

    # -------------------------------------------------------------- settings
    def get_settings(self):
        return {
            "ram_min_mb": self.settings.ram_min_mb,
            "ram_max_mb": self.settings.ram_max_mb,
            "java_path": self.settings.java_path,
            "base_dir": self.im.base_dir,
        }

    def save_settings(self, ram_min_mb, ram_max_mb, java_path):
        self.settings.ram_min_mb = int(ram_min_mb)
        self.settings.ram_max_mb = int(ram_max_mb)
        self.settings.java_path = java_path or ""
        self.settings.save()
        return self.get_settings()

    def get_console_minimized(self):
        return self.settings.console_minimized

    def set_console_minimized(self, minimized):
        self.settings.console_minimized = bool(minimized)
        self.settings.save()

    # -------------------------------------------------------- window chrome
    # The visible title bar is HTML, while core/winchrome.py handles its
    # dragging/hit-testing through the native Win32 window.
    #
    # own HTML/CSS; these are what its minimize/maximize/close buttons call.
    # Actual window-state changes go through core/winchrome.py, which calls
    # the real Win32 API on the window's real handle - so Windows performs
    # its own native minimize/maximize/restore, animations included, rather
    # than anything faked in the page.
    def window_start_drag(self):
        return winchrome.start_drag(self._window)

    def window_start_resize(self, edge):
        return winchrome.start_resize(self._window, edge)

    def window_minimize(self):
        winchrome.minimize(self._window)

    def window_toggle_maximize(self):
        winchrome.toggle_maximize(self._window)

    def window_close(self):
        winchrome.close(self._window)

    def window_is_maximized(self):
        return winchrome.is_maximized(self._window)

    # ----------------------------------------------------------- patch notes
    # Fetched server-side (via requests) rather than with fetch() in the page,
    # so it works regardless of the file:// origin's CORS restrictions inside
    # the native webview. Image URLs are made absolute for <img> use.
    _PATCH_BASE = "https://launchercontent.mojang.com"

    def get_patch_notes(self, limit=40):
        import requests
        try:
            r = requests.get(f"{self._PATCH_BASE}/v2/javaPatchNotes.json", timeout=15)
            r.raise_for_status()
            data = r.json()
            entries = []
            for e in (data.get("entries") or [])[:limit]:
                img = (e.get("image") or {}).get("url") or ""
                entries.append({
                    "title": e.get("title"),
                    "version": e.get("version"),
                    "type": e.get("type"),
                    "date": e.get("date"),
                    "shortText": e.get("shortText"),
                    "contentPath": e.get("contentPath"),
                    "id": e.get("id"),
                    "image": (self._PATCH_BASE + img) if img.startswith("/") else img,
                })
            return {"entries": entries}
        except Exception as e:
            return {"error": str(e)}

    def get_patch_note_body(self, content_path):
        import requests
        if not content_path:
            return {"error": "No content path."}
        try:
            r = requests.get(f"{self._PATCH_BASE}/v2/{content_path}", timeout=15)
            r.raise_for_status()
            data = r.json()
            body = data.get("body", "") or ""
            # image srcs in the body are root-relative ("/v2/...") - absolutize
            body = body.replace('src="/', f'src="{self._PATCH_BASE}/').replace("src='/", f"src='{self._PATCH_BASE}/")
            img = (data.get("image") or {}).get("url") or ""
            return {
                "body": body,
                "title": data.get("title"),
                "version": data.get("version"),
                "type": data.get("type"),
                "date": data.get("date"),
                "image": (self._PATCH_BASE + img) if img.startswith("/") else img,
            }
        except Exception as e:
            return {"error": str(e)}

    # -------------------------------------------------------------- activity
    def list_tasks(self):
        return [_task_to_dict(t) for t in sorted(self.tasks.tasks.values(), key=lambda t: t.created_at, reverse=True)]

    def clear_finished_tasks(self):
        for tid in [tid for tid, t in list(self.tasks.tasks.items()) if t.status != "running"]:
            del self.tasks.tasks[tid]
        return self.list_tasks()
