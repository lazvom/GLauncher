"""
Account handling.

Offline accounts just need a username - a deterministic offline UUID is derived
so worlds/servers behave consistently between sessions.

Microsoft accounts use the OAuth2 Device Code flow. Mojang/Microsoft require every
third-party launcher to use its OWN Azure "Application (client) ID" - there's no
legitimate way around that (using someone else's client ID, e.g. a game console's,
means impersonating an app you don't own, which breaks Microsoft's and Mojang's
terms and risks the account getting flagged). The device code flow is however the
simplest possible way to use your own client ID: no redirect URI, no local server,
no copy/pasting a URL. One-time setup at https://portal.azure.com:
  1. App registrations -> New registration (any name, "Personal Microsoft accounts
     only").
  2. Authentication -> Advanced settings -> turn ON "Allow public client flows".
     (No redirect URI is needed for this flow at all.)
  3. Copy the Application (client) ID into the Accounts tab.

Login flow implemented here:
 1. We ask Microsoft for a short one-time code + a URL (microsoft.com/link).
 2. You open that URL on any device, sign in, and type in the code.
 3. We poll in the background until you finish, then exchange the resulting
    token for a Minecraft profile + access token via Xbox Live -> XSTS ->
    Minecraft (the same chain the official launcher uses).
"""
from __future__ import annotations

import json
import os
import time
import webbrowser
from dataclasses import dataclass, asdict
from typing import Optional

import requests
import minecraft_launcher_lib as mll

from .launcher import offline_uuid

DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
DEVICE_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
# Minecraft Services access tokens are always issued with this lifetime; used
# as the fallback when a given API response doesn't echo "expires_in" back.
MC_TOKEN_LIFETIME_SECONDS = 24 * 60 * 60
# Refresh proactively once this little time is left, rather than waiting for
# the token to actually expire - this is what keeps a long-idle session (open
# in the launcher without hitting Play, or the app left running overnight)
# from ever presenting an expired token to something like the Skins tab.
REFRESH_MARGIN_SECONDS = 30 * 60
DEVICE_CODE_SCOPE = "XboxLive.signin offline_access"


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
                self.accounts = [Account(**a) for a in data.get("accounts", [])]
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
                if changed:
                    self.save()
            except Exception:
                self.accounts = []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = {
            "accounts": [a.to_dict() for a in self.accounts],
            "active_index": self.active_index,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

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


class DeviceCodePending(Exception):
    """Raised internally while waiting - not an error, just means 'keep polling'."""


class MicrosoftDeviceCodeFlow:
    """OAuth2 Device Code login: no redirect URI, no local server, nothing to paste.
    You still need your own Azure client ID (see module docstring) - that part is a
    genuine Microsoft requirement and can't be skipped - but this is the least
    friction any launcher can offer around it."""

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
            data={"client_id": self.client_id, "scope": DEVICE_CODE_SCOPE},
            timeout=20,
        )
        data = resp.json()
        if resp.status_code != 200 or "device_code" not in data:
            raise RuntimeError(data.get("error_description", "Could not start device code sign-in."))
        self.device_code = data["device_code"]
        self.interval = data.get("interval", 5)
        return data

    def open_browser(self, verification_uri: str):
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
        """Finishes the Xbox Live -> XSTS -> Minecraft -> profile chain (same steps the
        official launcher uses) and returns a dict shaped like complete_login()'s result."""
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
