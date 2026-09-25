"""
Wraps Mojang's Minecraft Services API (api.minecraftservices.com) for
viewing and changing skins/capes on a signed-in Microsoft account. Uses the
same Minecraft access token already obtained during sign-in (core/auth.py) -
no extra authentication needed. Offline accounts have no real Mojang profile,
so none of this applies to them.

Endpoints per Mojang's own API (verified against current docs, Aug 2026):
  GET    /minecraft/profile               - profile incl. skins[] and capes[]
  POST   /minecraft/profile/skins         - set skin (multipart file OR JSON url)
  DELETE /minecraft/profile/skins/active  - reset to default Steve/Alex
  PUT    /minecraft/profile/capes/active  - equip an owned cape by id
  DELETE /minecraft/profile/capes/active  - unequip the active cape
"""
from __future__ import annotations

import requests

API_BASE = "https://api.minecraftservices.com/minecraft/profile"


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def get_profile(access_token: str) -> dict:
    """Returns {id, name, skins: [...], capes: [...]}. Each skin/cape entry has
    a 'state' of ACTIVE or INACTIVE and a 'url' pointing at the texture PNG."""
    resp = requests.get(API_BASE, headers=_headers(access_token), timeout=20)
    if resp.status_code == 404:
        raise ValueError("This account doesn't own a copy of Minecraft.")
    resp.raise_for_status()
    return resp.json()


def set_skin_from_url(access_token: str, url: str, variant: str = "classic") -> dict:
    """variant is 'classic' (Steve model) or 'slim' (Alex model)."""
    resp = requests.post(
        f"{API_BASE}/skins",
        headers={**_headers(access_token), "Content-Type": "application/json"},
        json={"url": url, "variant": variant},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def upload_skin_file(access_token: str, file_path: str, variant: str = "classic") -> dict:
    """Uploads a local PNG file as the account's new skin."""
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/skins",
            headers=_headers(access_token),
            data={"variant": variant},
            files={"file": ("skin.png", f, "image/png")},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


def reset_skin(access_token: str) -> dict:
    """Removes the custom skin, reverting to the default Steve/Alex model."""
    resp = requests.delete(f"{API_BASE}/skins/active", headers=_headers(access_token), timeout=20)
    resp.raise_for_status()
    return resp.json()


def set_active_cape(access_token: str, cape_id: str) -> dict:
    resp = requests.put(
        f"{API_BASE}/capes/active",
        headers={**_headers(access_token), "Content-Type": "application/json"},
        json={"capeId": cape_id},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def clear_active_cape(access_token: str) -> dict:
    resp = requests.delete(f"{API_BASE}/capes/active", headers=_headers(access_token), timeout=20)
    resp.raise_for_status()
    return resp.json()
