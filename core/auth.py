"""
Account handling.

Offline accounts just need a username - a deterministic offline UUID is derived
so worlds/servers behave consistently between sessions.

Microsoft accounts use OAuth2. Mojang/Microsoft require every third-party
launcher to use its OWN Azure "Application (client) ID" - there's no legitimate
way around that (using someone else's client ID, e.g. a game console's or one
copied from a tutorial/gist, means impersonating an app you don't own, which
breaks Microsoft's and Mojang's terms and risks the account getting flagged).
One-time setup at https://portal.azure.com:
  1. App registrations -> New registration (any name, "Personal Microsoft
     accounts only").
  2. Authentication -> Advanced settings -> turn ON "Allow public client flows".
  3. Still on Authentication -> Add a platform -> "Mobile and desktop
     applications" -> add the exact redirect URI AUTH_CODE_REDIRECT_URI below
     as a Custom redirect URI. (Only needed for MicrosoftAuthCodeFlow, the
     no-code-to-type flow below - MicrosoftDeviceCodeFlow doesn't use a
     redirect URI at all, which is why it used to be the only flow here.)
  4. Copy the Application (client) ID into the Accounts tab.

Two login flows are implemented here, both ending at the same place (an
MSA access token to hand to complete_ms_login()):

MicrosoftAuthCodeFlow - the default. Opens the browser straight to
Microsoft's sign-in page; a one-shot local HTTP server on 127.0.0.1 catches
the redirect Microsoft sends back once you're signed in, so there's no code
to read or type anywhere - the tab just closes itself. This needs the extra
one-time redirect URI setup above.

MicrosoftDeviceCodeFlow - the fallback ("Use a code instead" in the sign-in
sheet), for whenever the local server can't be used (a firewall/AV blocking
it, a locked-down network, or the redirect URI hasn't been added yet): shows
a short code, you enter it at a Microsoft page on any device. No redirect URI
needed for this one at all.
"""
from __future__ import annotations

import http.server
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, asdict
from typing import Optional

import requests
import minecraft_launcher_lib as mll

from .launcher import offline_uuid
from .security import protect_file_permissions, protect_secret, unprotect_secret

DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
DEVICE_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
AUTH_CODE_AUTHORIZE_URL = "https://login.live.com/oauth20_authorize.srf"
AUTH_CODE_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
# Azure's redirect-URI matching ignores the port for plain "localhost"
# registrations (per RFC 8252 / Microsoft's own docs), which would let a
# random free port be picked at runtime instead of a fixed one - but that
# behavior is documented for the modern login.microsoftonline.com surface,
# and this flow has to use the older login.live.com surface specifically to
# get the XboxLive.signin scope, so a literal, exact-match port is used
# instead of relying on that: one specific, unusual port registered exactly
# once, and always bound to exactly that port here.
AUTH_CODE_PORT = 47825
AUTH_CODE_REDIRECT_URI = f"http://127.0.0.1:{AUTH_CODE_PORT}/"
# Minecraft Services access tokens are always issued with this lifetime; used
# as the fallback when a given API response doesn't echo "expires_in" back.
MC_TOKEN_LIFETIME_SECONDS = 24 * 60 * 60
# Refresh proactively once this little time is left, rather than waiting for
# the token to actually expire - this is what keeps a long-idle session (open
# in the launcher without hitting Play, or the app left running overnight)
# from ever presenting an expired token to something like the Skins tab.
REFRESH_MARGIN_SECONDS = 30 * 60
MS_LOGIN_SCOPE = "XboxLive.signin offline_access"


def format_uuid(raw: str) -> str:
    """Ensures a Mojang/Xbox profile UUID has standard dashes (8-4-4-4-12).

    Mojang's Minecraft-profile API (what login_data['id'] comes from) returns
    the UUID *without* dashes. If that raw string is passed straight through
    as the --uuid launch argument, sign-in still succeeds but the game's
    skin/cape lookup against Mojang's session servers can silently fail to
    match it, and you get the default Steve/Alex model instead of your real
    skin even though you're properly logged in."""
    stripped = raw.replace("-", "")
    if len(stripped) != 32:
        return raw  # not a recognizable UUID - leave it alone rather than mangle it
    return f"{stripped[0:8]}-{stripped[8:12]}-{stripped[12:16]}-{stripped[16:20]}-{stripped[20:32]}"


@dataclass
class Account:
    kind: str  # "offline" or "microsoft"
    username: str
    uuid: str
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0

    def to_dict(self):
        return asdict(self)


class AccountStore:
    def __init__(self, path: str):
        self.path = path
        self.accounts: list[Account] = []
        self.active_index: int = -1
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.accounts = []
                secrets_need_migration = False
                for raw in data.get("accounts", []):
                    item = dict(raw)
                    if item.get("access_token") and not str(item.get("access_token")).startswith("dpapi:"):
                        secrets_need_migration = True
                    if item.get("refresh_token") and not str(item.get("refresh_token")).startswith("dpapi:"):
                        secrets_need_migration = True
                    try:
                        item["access_token"] = unprotect_secret(item.get("access_token", ""))
                        item["refresh_token"] = unprotect_secret(item.get("refresh_token", ""))
                    except Exception:
                        # Do not silently turn an unreadable encrypted account
                        # into a logged-out account; surface it as unavailable.
                        item["access_token"] = ""
                        item["refresh_token"] = ""
                    self.accounts.append(Account(**item))
                self.active_index = data.get("active_index", -1)
                # migrate accounts saved before UUIDs were dash-formatted (the cause
                # of skins/capes not loading in game despite a successful sign-in)
                changed = False
                for acc in self.accounts:
                    if acc.kind == "microsoft":
                        fixed = format_uuid(acc.uuid)
                        if fixed != acc.uuid:
                            acc.uuid = fixed
                            changed = True
                if changed or secrets_need_migration:
                    self.save()
            except Exception:
                self.accounts = []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = {
            "accounts": [],
            "active_index": self.active_index,
        }
        for account in self.accounts:
            item = account.to_dict()
            item["access_token"] = protect_secret(item.get("access_token", ""))
            item["refresh_token"] = protect_secret(item.get("refresh_token", ""))
            data["accounts"].append(item)

        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self.path)
        protect_file_permissions(self.path)

    def add_offline(self, username: str) -> Account:
        acc = Account(kind="offline", username=username, uuid=offline_uuid(username))
        self.accounts.append(acc)
        self.active_index = len(self.accounts) - 1
        self.save()
        return acc

    def add_microsoft(self, login_data: dict) -> Account:
        acc = Account(
            kind="microsoft",
            username=login_data["name"],
            uuid=format_uuid(login_data["id"]),
            access_token=login_data.get("access_token", ""),
            refresh_token=login_data.get("refresh_token", ""),
            expires_at=login_data.get("expires_at", 0),
        )
        # replace an existing account with the same uuid, if re-logging in
        for i, existing in enumerate(self.accounts):
            if existing.uuid == acc.uuid:
                self.accounts[i] = acc
                self.active_index = i
                self.save()
                return acc
        self.accounts.append(acc)
        self.active_index = len(self.accounts) - 1
        self.save()
        return acc

    def remove(self, index: int):
        if 0 <= index < len(self.accounts):
            del self.accounts[index]
            if self.active_index >= len(self.accounts):
                self.active_index = len(self.accounts) - 1
            self.save()

    def set_active(self, index: int):
        if 0 <= index < len(self.accounts):
            self.active_index = index
            self.save()

    def get_active(self) -> Optional[Account]:
        if 0 <= self.active_index < len(self.accounts):
            return self.accounts[self.active_index]
        return None

    def refresh_if_needed(self, index: int, azure_client_id: str, force: bool = False) -> Account:
        """Try to refresh a Microsoft account's token. Skips the network round-trip
        entirely if the current token still has plenty of time left - unless
        force=True, which is used right before actually launching the game, where
        it's worth the extra request to guarantee the freshest possible session."""
        acc = self.accounts[index]
        if acc.kind != "microsoft" or not acc.refresh_token or not azure_client_id:
            return acc
        if not force and acc.expires_at and acc.expires_at - time.time() > REFRESH_MARGIN_SECONDS:
            return acc
        try:
            login_data = mll.microsoft_account.complete_refresh(
                azure_client_id, None, None, acc.refresh_token
            )
            acc.access_token = login_data["access_token"]
            acc.refresh_token = login_data.get("refresh_token", acc.refresh_token)
            acc.username = login_data["name"]
            acc.uuid = format_uuid(login_data["id"])
            acc.expires_at = time.time() + MC_TOKEN_LIFETIME_SECONDS
            self.accounts[index] = acc
            self.save()
        except Exception:
            pass
        return acc


def complete_ms_login(ms_token_data: dict) -> dict:
    """Finishes the Xbox Live -> XSTS -> Minecraft -> profile chain (same steps the
    official launcher uses) and returns a dict shaped like complete_login()'s result.
    Shared by both login flows below - everything from here on is identical
    regardless of whether the access_token came from the device code flow or
    the auth code flow."""
    access_token = ms_token_data["access_token"]

    xbl = mll.microsoft_account.authenticate_with_xbl(access_token)
    if "Token" not in xbl:
        raise RuntimeError("Xbox Live authentication failed. Try signing in again.")
    xbl_token = xbl["Token"]
    userhash = xbl["DisplayClaims"]["xui"][0]["uhs"]

    xsts = mll.microsoft_account.authenticate_with_xsts(xbl_token)
    if "Token" not in xsts:
        raise RuntimeError("Xbox Live sign-in check failed (XSTS). Make sure the account has an Xbox profile.")
    xsts_token = xsts["Token"]

    mc_auth = mll.microsoft_account.authenticate_with_minecraft(userhash, xsts_token)
    if "access_token" not in mc_auth:
        # Mojang's own API returns a specific reason here (rate limiting, a
        # malformed/expired token, a service outage, etc.) - surface that
        # instead of always guessing "check Allow public client flows",
        # which is misleading when that setting is already correct and
        # something else entirely is the real cause.
        detail = mc_auth.get("errorMessage") or mc_auth.get("error") or mc_auth.get("developerMessage")
        if detail:
            raise RuntimeError(f"Minecraft authentication failed: {detail}")
        raise RuntimeError(
            "Minecraft authentication failed for this Azure app. Double-check "
            "'Allow public client flows' is enabled, and that you signed in with "
            "a Microsoft account that owns Minecraft."
        )
    mc_access_token = mc_auth["access_token"]

    profile = mll.microsoft_account.get_profile(mc_access_token)
    if profile.get("error") == "NOT_FOUND":
        raise RuntimeError("This Microsoft account doesn't own Minecraft.")

    profile["access_token"] = mc_access_token
    profile["refresh_token"] = ms_token_data.get("refresh_token", "")
    profile["expires_at"] = time.time() + mc_auth.get("expires_in", MC_TOKEN_LIFETIME_SECONDS)
    return profile


class DeviceCodePending(Exception):
    """Raised internally while waiting - not an error, just means 'keep polling'."""


class MicrosoftDeviceCodeFlow:
    """OAuth2 Device Code login: no redirect URI, no local server - the
    fallback flow (see module docstring) for whenever MicrosoftAuthCodeFlow's
    local listener can't be used. You still need your own Azure client ID
    (see module docstring) - that part is a genuine Microsoft requirement
    and can't be skipped - but no extra redirect URI setup is needed for
    this one specifically."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.device_code: Optional[str] = None
        self.interval: int = 5
        self._cancelled = False

    def request_code(self) -> dict:
        """Asks Microsoft for a user_code + verification_uri. Returns the raw response
        dict (keys: user_code, verification_uri, message, expires_in, interval)."""
        resp = requests.post(
            DEVICE_CODE_URL,
            data={"client_id": self.client_id, "scope": MS_LOGIN_SCOPE},
            timeout=20,
        )
        data = resp.json()
        if resp.status_code != 200 or "device_code" not in data:
            raise RuntimeError(data.get("error_description", "Could not start device code sign-in."))
        self.device_code = data["device_code"]
        self.interval = data.get("interval", 5)
        return data

    def open_browser(self, verification_uri: str, user_code: str = ""):
        """Opens the sign-in page. The code still has to be typed in by
        hand on that page - an earlier version of this tried appending the
        code as a "?otc=" query parameter to pre-fill it, on the theory
        that the microsoft.com page accepts that the way a couple other
        third-party Minecraft launchers' source seemed to rely on. In
        practice that didn't work (confirmed by testing against a real
        account), and it lines up with what Microsoft's own device-code
        docs say: the standard OAuth "verification_uri_complete" field
        isn't returned or supported for this endpoint at all. So this just
        opens the plain page - `user_code` is kept as a parameter so
        callers don't need updating if a genuinely working pre-fill method
        turns up later, but nothing is done with it right now."""
        webbrowser.open(verification_uri)

    def cancel(self):
        self._cancelled = True

    def poll_for_token(self, expires_in: int = 900) -> dict:
        """Blocks (call from a background thread), polling Microsoft until the person
        finishes entering the code elsewhere, or the code expires / is cancelled."""
        if not self.device_code:
            raise RuntimeError("request_code() must be called first.")
        deadline = time.time() + expires_in
        while time.time() < deadline:
            if self._cancelled:
                raise RuntimeError("Sign-in cancelled.")
            resp = requests.post(
                DEVICE_TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.client_id,
                    "device_code": self.device_code,
                },
                timeout=20,
            )
            data = resp.json()
            if resp.status_code == 200 and "access_token" in data:
                return data
            error = data.get("error", "")
            if error == "authorization_pending":
                time.sleep(self.interval)
                continue
            if error == "slow_down":
                self.interval += 5
                time.sleep(self.interval)
                continue
            raise RuntimeError(data.get("error_description", error or "Sign-in failed."))
        raise TimeoutError("The sign-in code expired before you finished. Try again.")

    def complete(self, ms_token_data: dict) -> dict:
        return complete_ms_login(ms_token_data)


class _RedirectCatcherHandler(http.server.BaseHTTPRequestHandler):
    """Handles exactly the one incoming request Microsoft's redirect makes,
    grabs its query string, and shows a plain "you can close this" page -
    nothing here talks to Microsoft, it just catches what Microsoft already
    sent to this machine."""

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        self.server.result = urllib.parse.parse_qs(query)  # type: ignore[attr-defined]
        ok = "code" in self.server.result  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        heading = "Signed in" if ok else "Sign-in didn't complete"
        self.wfile.write(
            f"<html><body style='font-family:sans-serif;text-align:center;padding-top:80px'>"
            f"<h2>{heading}</h2><p>You can close this tab and go back to GLauncher.</p>"
            f"</body></html>".encode("utf-8")
        )

    def log_message(self, format, *args):
        pass  # don't spam stderr with request logging for a one-shot local listener


class MicrosoftAuthCodeFlow:
    """OAuth2 Authorization Code login via a one-shot local HTTP listener -
    the default flow (see module docstring): nothing to read or type
    anywhere, the browser tab just closes itself once you're signed in.
    Needs the one-time redirect URI setup in the module docstring; falls
    back to MicrosoftDeviceCodeFlow automatically in the sign-in sheet if
    starting the local listener fails (something else already using
    AUTH_CODE_PORT, a firewall blocking it, etc.)."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self._server: Optional[http.server.HTTPServer] = None
        self._state = secrets.token_urlsafe(16)
        self._cancelled = False

    def start(self) -> str:
        """Starts the local listener and returns the Microsoft sign-in URL
        to open in a browser. Raises OSError if AUTH_CODE_PORT is already
        in use - callers should fall back to the device code flow then."""
        self._server = http.server.HTTPServer(("127.0.0.1", AUTH_CODE_PORT), _RedirectCatcherHandler)
        self._server.timeout = 1  # lets wait_for_code() poll _cancelled instead of blocking forever
        self._server.result = None  # type: ignore[attr-defined]
        query = urllib.parse.urlencode({
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": AUTH_CODE_REDIRECT_URI,
            "scope": MS_LOGIN_SCOPE,
            "state": self._state,
        })
        return f"{AUTH_CODE_AUTHORIZE_URL}?{query}"

    def open_browser(self, url: str):
        webbrowser.open(url)

    def cancel(self):
        self._cancelled = True

    def _first(self, params: dict, key: str, default: str = "") -> str:
        values = params.get(key)
        return values[0] if values else default

    def wait_for_code(self, timeout: int = 900) -> str:
        """Blocks (call from a background thread) until the browser redirect
        actually lands, or the wait times out / is cancelled."""
        if not self._server:
            raise RuntimeError("start() must be called first.")
        deadline = time.time() + timeout
        try:
            while self._server.result is None:  # type: ignore[attr-defined]
                if self._cancelled:
                    raise RuntimeError("Sign-in cancelled.")
                if time.time() >= deadline:
                    raise TimeoutError("Sign-in didn't complete in time. Try again.")
                self._server.handle_request()  # blocks up to self._server.timeout seconds
        finally:
            self._server.server_close()

        params = self._server.result  # type: ignore[attr-defined]
        if "error" in params:
            raise RuntimeError(self._first(params, "error_description") or self._first(params, "error", "Sign-in failed."))
        if self._first(params, "state") != self._state:
            raise RuntimeError("Sign-in response didn't match - try again.")
        code = self._first(params, "code")
        if not code:
            raise RuntimeError("No authorization code was returned.")
        return code

    def exchange_code(self, code: str) -> dict:
        resp = requests.post(
            AUTH_CODE_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": AUTH_CODE_REDIRECT_URI,
                "scope": MS_LOGIN_SCOPE,
            },
            timeout=20,
        )
        data = resp.json()
        if resp.status_code != 200 or "access_token" not in data:
            raise RuntimeError(data.get("error_description", "Could not complete sign-in."))
        return data

    def complete(self, ms_token_data: dict) -> dict:
        return complete_ms_login(ms_token_data)
