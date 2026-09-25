"""
Instance model.

Layout on disk (default base directory: <launcher folder>/data):
  data/
    shared/              <- versions/, libraries/, assets/ (shared across instances, saves disk space)
    instances/
      <instance-id>/
        instance.json    <- metadata for this instance
        mods/
        resourcepacks/
        shaderpacks/
        saves/
        config/
    accounts.json
    settings.json

Everything the launcher generates lives next to the launcher itself (portable
install) rather than in the user's home directory, so the whole app can be
moved, copied, or zipped up as one self-contained folder.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
import uuid as uuidlib
from dataclasses import dataclass, asdict, field
from typing import Optional


def _launcher_root() -> str:
    """Folder the launcher itself lives in: the folder containing the
    packaged executable when frozen (e.g. via PyInstaller), or the project's
    top-level folder (one above core/) when run from source. This is
    deliberately NOT the same as a frozen app's temp extraction directory
    (sys._MEIPASS), which gets wiped between runs and can't hold persistent
    data."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_base_dir() -> str:
    return os.path.join(_launcher_root(), "data")


def _migrate_legacy_home_dir(base_dir: str) -> None:
    """One-time migration: earlier versions stored everything in
    ~/GlassLauncher. If that legacy folder exists and the new portable data
    folder doesn't yet, move it over so accounts/instances created before
    this change aren't lost."""
    legacy_dir = os.path.join(os.path.expanduser("~"), "GlassLauncher")
    if os.path.abspath(legacy_dir) == os.path.abspath(base_dir):
        return
    if os.path.isdir(legacy_dir) and not os.path.exists(base_dir):
        try:
            shutil.move(legacy_dir, base_dir)
        except OSError:
            pass  # worst case the user re-signs-in / re-creates instances


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
    return slug or "instance"


@dataclass
class Instance:
    id: str
    name: str
    mc_version: str
    loader: str  # vanilla / fabric / quilt / forge / neoforge
    loader_version: Optional[str] = None
    installed_version_id: Optional[str] = None  # version id passed to get_minecraft_command
    created_at: float = field(default_factory=time.time)
    ram_min_mb: int = 1024
    ram_max_mb: int = 4096
    jvm_args: str = ""
    installed: bool = False

    def to_dict(self):
        return asdict(self)


class InstanceManager:
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = default_base_dir()
            _migrate_legacy_home_dir(base_dir)
        self.base_dir = base_dir
        self.shared_dir = os.path.join(self.base_dir, "shared")
        self.instances_dir = os.path.join(self.base_dir, "instances")
        os.makedirs(self.shared_dir, exist_ok=True)
        os.makedirs(self.instances_dir, exist_ok=True)
        self.instances: list[Instance] = []
        self._lock = threading.Lock()
        # Multiple instances can share the same underlying vanilla/loader files
        # (that's the point of shared_dir - it saves disk space). But if two
        # installs happen to need the *same* library/asset file at the same
        # time, they can race writing to it and corrupt it for both - that's
        # what "wrong Checksum" errors during a download mean. This lock
        # serializes actual writes into shared_dir so that can't happen;
        # installs still run concurrently in every other sense (their own
        # background tasks, their own progress, no UI blocking), they just
        # take turns for the part that touches shared files.
        self.shared_install_lock = threading.Lock()
        self._load_all()

    # ---------------------------------------------------------------- utils
    def instance_dir(self, instance_id: str) -> str:
        return os.path.join(self.instances_dir, instance_id)

    def _meta_path(self, instance_id: str) -> str:
        return os.path.join(self.instance_dir(instance_id), "instance.json")

    def _load_all(self):
        self.instances = []
        if not os.path.isdir(self.instances_dir):
            return
        for entry in sorted(os.listdir(self.instances_dir)):
            meta_path = os.path.join(self.instances_dir, entry, "instance.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.instances.append(Instance(**data))
                except Exception:
                    continue

    def save(self, inst: Instance):
        d = self.instance_dir(inst.id)
        os.makedirs(d, exist_ok=True)
        for sub in ("mods", "resourcepacks", "shaderpacks", "saves", "config"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        with open(self._meta_path(inst.id), "w", encoding="utf-8") as f:
            json.dump(inst.to_dict(), f, indent=2)

    # ------------------------------------------------------------- installed content manifest
    def _content_manifest_path(self, instance_id: str) -> str:
        return os.path.join(self.instance_dir(instance_id), "content.json")

    def get_installed_content(self, instance_id: str) -> dict:
        """Returns {project_id: {"version_id", "filename", "project_type"}} for everything
        this launcher has installed into the instance (used to skip re-downloading mods
        that are already there, e.g. as a shared dependency of two other mods)."""
        path = self._content_manifest_path(instance_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    # Which instance subfolder each content type's files live in.
    _CONTENT_SUBFOLDER = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}

    def record_installed_content(self, instance_id: str, project_id: str, version_id: str,
                                  filename: str, project_type: str, name: Optional[str] = None,
                                  icon_url: Optional[str] = None):
        if not project_id:
            return
        with self._lock:
            manifest = self.get_installed_content(instance_id)
            existing = manifest.get(project_id, {})
            # a caller that doesn't know the display name/icon (e.g. installing
            # a raw dependency) shouldn't blow away one we already cached
            if name is None:
                name = existing.get("name")
            if icon_url is None:
                icon_url = existing.get("icon_url")
            entry = {"version_id": version_id, "filename": filename, "project_type": project_type}
            if name:
                entry["name"] = name
            if icon_url:
                entry["icon_url"] = icon_url
            manifest[project_id] = entry
            with open(self._content_manifest_path(instance_id), "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

    def _write_manifest(self, instance_id: str, manifest: dict):
        with open(self._content_manifest_path(instance_id), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def remove_installed_content(self, instance_id: str, project_id: str):
        """Drops just the manifest record, without touching any file."""
        with self._lock:
            manifest = self.get_installed_content(instance_id)
            if project_id in manifest:
                del manifest[project_id]
                self._write_manifest(instance_id, manifest)

    def delete_installed_content(self, instance_id: str, project_id: Optional[str] = None,
                                  filename: Optional[str] = None, project_type: Optional[str] = None) -> dict:
        """Deletes the actual file *and* its manifest record - what the Manage tab
        uses. Returns {"ok": True} or {"error": ...}. Content the launcher never
        installed (no project_id - the user dropped the file in by hand) has no
        manifest record to clean up; deletes it by filename/subfolder instead."""
        if project_id:
            entry = self.get_installed_content(instance_id).get(project_id)
            if not entry:
                return {"error": "Not installed."}
            subfolder = self._CONTENT_SUBFOLDER.get(entry.get("project_type"), "mods")
            file_path = os.path.join(self.instance_dir(instance_id), subfolder, entry.get("filename", ""))
        else:
            if not filename or not project_type:
                return {"error": "Not installed."}
            subfolder = self._CONTENT_SUBFOLDER.get(project_type, "mods")
            file_path = os.path.join(self.instance_dir(instance_id), subfolder, filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            return {"error": str(e)}
        if project_id:
            self.remove_installed_content(instance_id, project_id)
        return {"ok": True}

    def list_installed_content(self, instance_id: str) -> list:
        """Installed content as a list (with project_id folded in), for the Manage
        tab. Self-heals: if a file was deleted outside the app (or by a version of
        the app before this existence check existed), its stale manifest record is
        dropped here instead of permanently blocking reinstall of that content.

        Also picks up files sitting in mods/resourcepacks/shaderpacks that were
        never installed through GLauncher (dropped in by hand) - those come back
        with project_id None and no name/icon, so the Manage tab shows just their
        raw filename."""
        manifest = self.get_installed_content(instance_id)
        result = []
        stale = []
        known_filenames = {}  # project_type -> set of filenames already accounted for
        for project_id, entry in manifest.items():
            subfolder = self._CONTENT_SUBFOLDER.get(entry.get("project_type"), "mods")
            file_path = os.path.join(self.instance_dir(instance_id), subfolder, entry.get("filename", ""))
            if os.path.exists(file_path):
                result.append({"project_id": project_id, **entry})
                known_filenames.setdefault(entry.get("project_type"), set()).add(entry.get("filename"))
            else:
                stale.append(project_id)
        if stale:
            with self._lock:
                fresh = self.get_installed_content(instance_id)
                for pid in stale:
                    fresh.pop(pid, None)
                self._write_manifest(instance_id, fresh)

        for project_type, subfolder in self._CONTENT_SUBFOLDER.items():
            folder_path = os.path.join(self.instance_dir(instance_id), subfolder)
            if not os.path.isdir(folder_path):
                continue
            already = known_filenames.get(project_type, set())
            try:
                entries = os.listdir(folder_path)
            except OSError:
                continue
            for filename in entries:
                if filename in already:
                    continue
                if not os.path.isfile(os.path.join(folder_path, filename)):
                    continue
                if filename.startswith("."):
                    continue
                result.append({"project_id": None, "filename": filename, "project_type": project_type})
        return result

    def is_content_installed(self, instance_id: str, project_id: str, version_id: Optional[str] = None) -> bool:
        entry = self.get_installed_content(instance_id).get(project_id)
        if not entry:
            return False
        if version_id and entry.get("version_id") != version_id:
            return False  # a different version is installed - not the same install
        subfolder = self._CONTENT_SUBFOLDER.get(entry.get("project_type"), "mods")
        file_path = os.path.join(self.instance_dir(instance_id), subfolder, entry.get("filename", ""))
        if not os.path.exists(file_path):
            # the file is gone (deleted via Manage, or by hand) but the record
            # wasn't cleaned up - drop it now instead of blocking reinstall forever
            self.remove_installed_content(instance_id, project_id)
            return False
        return True

    def create(self, name: str, mc_version: str, loader: str, loader_version: Optional[str] = None) -> Instance:
        with self._lock:
            base_id = _slugify(name)
            inst_id = base_id
            n = 1
            existing_ids = {i.id for i in self.instances}
            while inst_id in existing_ids or os.path.exists(self.instance_dir(inst_id)):
                n += 1
                inst_id = f"{base_id}-{n}"

            inst = Instance(
                id=inst_id,
                name=name,
                mc_version=mc_version,
                loader=loader,
                loader_version=loader_version,
            )
            self.save(inst)
            self.instances.append(inst)
            return inst

    def delete(self, instance_id: str, delete_files: bool = True):
        with self._lock:
            self.instances = [i for i in self.instances if i.id != instance_id]
            if delete_files:
                import shutil

                d = self.instance_dir(instance_id)
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)

    def get(self, instance_id: str) -> Optional[Instance]:
        for i in self.instances:
            if i.id == instance_id:
                return i
        return None

    def mark_installed(self, instance_id: str, installed_version_id: str):
        with self._lock:
            inst = self.get(instance_id)
            if inst:
                inst.installed = True
                inst.installed_version_id = installed_version_id
                self.save(inst)
