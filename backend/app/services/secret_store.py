from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from app.config import settings


class SecretStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _secret_path() -> Path:
    return settings.data_dir / "secrets" / "gemini-api-key.dpapi"


def _page_secret_path(page_id: str) -> Path:
    if not page_id.isdigit() or len(page_id) > 40:
        raise ValueError("Facebook Page ID ไม่ถูกต้อง")
    return settings.data_dir / "secrets" / f"facebook-page-{page_id}.dpapi"


def _write_secret(path: Path, value: str, description: str) -> None:
    if len(value) < 20 or len(value) > 4096 or "\n" in value or "\r" in value:
        raise ValueError("รูปแบบ access token ไม่ถูกต้อง")
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = _windows_dpapi(True, value.encode("utf-8"))
    temp = path.with_suffix(".tmp")
    temp.write_bytes(encrypted)
    os.replace(temp, path)


def _read_secret(path: Path, description: str) -> str | None:
    if not path.is_file():
        return None
    try:
        raw = _windows_dpapi(False, path.read_bytes()).decode("utf-8")
    except (OSError, UnicodeDecodeError, SecretStoreError) as exc:
        raise SecretStoreError(f"อ่าน {description} ที่เข้ารหัสไว้ไม่สำเร็จ ต้องบันทึกใหม่") from exc
    return raw or None


def _windows_dpapi(encrypt: bool, value: bytes) -> bytes:
    if os.name != "nt":
        raise SecretStoreError("การเก็บคีย์แบบเข้ารหัสนี้ต้องใช้ Windows")
    crypt32 = ctypes.WinDLL("Crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
    input_buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    input_blob = _DataBlob(len(value), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _DataBlob()
    protect = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    if encrypt:
        protect.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
        protect.restype = wintypes.BOOL
        ok = protect(ctypes.byref(input_blob), "KodKon Studio Gemini key", None, None, None, 0x1, ctypes.byref(output_blob))
    else:
        protect.argtypes = [ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
        protect.restype = wintypes.BOOL
        description = wintypes.LPWSTR()
        ok = protect(ctypes.byref(input_blob), ctypes.byref(description), None, None, None, 0x1, ctypes.byref(output_blob))
        if description:
            kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))
    if not ok:
        raise SecretStoreError(f"Windows ปกป้องข้อมูลลับไม่สำเร็จ (รหัส {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def save_gemini_key(api_key: str) -> None:
    key = api_key.strip()
    _write_secret(_secret_path(), key, "KodKon Studio Gemini key")


def load_gemini_key() -> str | None:
    return _read_secret(_secret_path(), "Gemini API key")


def delete_gemini_key() -> None:
    _secret_path().unlink(missing_ok=True)


def save_facebook_page_token(page_id: str, access_token: str) -> None:
    _write_secret(_page_secret_path(page_id), access_token.strip(), f"KodKon Studio Facebook Page {page_id} token")


def load_facebook_page_token(page_id: str) -> str | None:
    return _read_secret(_page_secret_path(page_id), f"Facebook Page {page_id} token")


def delete_facebook_page_token(page_id: str) -> None:
    _page_secret_path(page_id).unlink(missing_ok=True)
