"""Security helpers for filesystem, URL, and stored-secret handling."""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import os
import re
from pathlib import Path

_INSTANCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def validate_instance_id(instance_id: str) -> str:
    value = str(instance_id or "")
    if not _INSTANCE_ID_RE.fullmatch(value):
        raise ValueError("Invalid instance id.")
    return value


def safe_filename(filename: str, *, max_length: int = 255) -> str:
    value = str(filename or "")
    if not value or "\x00" in value:
        raise ValueError("Invalid filename.")
    p = Path(value)
    # Reject traversal, absolute paths, Windows separators/drive prefixes, and
    # other platform-specific path syntax rather than silently flattening it.
    if (p.name != value or p.is_absolute() or value in {".", ".."}
            or "/" in value or "\\" in value or ":" in value):
        raise ValueError("Invalid filename.")
    if len(value) > max_length:
        raise ValueError("Filename is too long.")
    if value.rstrip(" .") != value:
        raise ValueError("Invalid filename.")
    return value


def ensure_within_directory(base_dir: str, target_path: str) -> str:
    base = Path(base_dir).resolve()
    target = Path(target_path).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("Path escapes its allowed directory.") from exc
    return str(target)


def is_https_host(url: str, allowed_hosts: set[str]) -> bool:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(str(url))
    except Exception:
        return False
    return (
        parsed.scheme.lower() == "https"
        and not parsed.username
        and not parsed.password
        and (parsed.hostname or "").lower() in allowed_hosts
    )


# ---------------------------------------------------------------------------
# Windows DPAPI. On non-Windows platforms we keep the existing JSON format and
# apply restrictive file permissions instead; the launcher is primarily shipped
# for Windows, and this avoids adding another third-party crypto dependency.

_DPAPI_PREFIX = "dpapi:"


if os.name == "nt":
    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL


def protect_secret(value: str) -> str:
    if not value:
        return ""
    if os.name != "nt":
        return value
    raw = value.encode("utf-8")
    in_buf = ctypes.create_string_buffer(raw)
    in_blob = _DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "GLauncher secret",
        None,
        None,
        None,
        1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "Windows DPAPI encryption failed")
    try:
        encoded = base64.b64encode(ctypes.string_at(out_blob.pbData, out_blob.cbData)).decode("ascii")
        return _DPAPI_PREFIX + encoded
    finally:
        _kernel32.LocalFree(out_blob.pbData)


def unprotect_secret(value: str) -> str:
    if not value or not value.startswith(_DPAPI_PREFIX):
        return value or ""
    if os.name != "nt":
        raise RuntimeError("Encrypted account data can only be decrypted on Windows.")
    try:
        raw = base64.b64decode(value[len(_DPAPI_PREFIX):], validate=True)
    except Exception as exc:
        raise ValueError("Invalid encrypted secret.") from exc
    in_buf = ctypes.create_string_buffer(raw)
    in_blob = _DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    description = wintypes.LPWSTR()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        ctypes.byref(description),
        None,
        None,
        None,
        1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "Windows DPAPI decryption failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
    finally:
        if description:
            _kernel32.LocalFree(description)
        _kernel32.LocalFree(out_blob.pbData)


def protect_file_permissions(path: str) -> None:
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
