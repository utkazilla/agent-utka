"""Protect a local setting with Windows user-scoped DPAPI."""

import base64
import binascii
import ctypes
import sys
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]


def _dpapi(data, *, protect):
    if sys.platform != "win32":
        raise OSError("Хранение ключей OpenAI доступно в Windows.")
    buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.c_void_p))
    result = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32")
    operation = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    operation.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    operation.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    try:
        if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
            raise OSError("Windows не удалось обработать сохранённый ключ OpenAI.")
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.memset(buffer, 0, len(buffer))
        if result.data:
            ctypes.memset(result.data, 0, result.size)
            kernel32.LocalFree(result.data)


def protect_key(key):
    return base64.b64encode(_dpapi(key.encode("utf-8"), protect=True)).decode("ascii") if key else ""


def unprotect_key(value):
    if not value:
        return ""
    try:
        return _dpapi(base64.b64decode(value, validate=True), protect=False).decode("utf-8")
    except (binascii.Error, UnicodeError, TypeError, ValueError):
        raise ValueError("Сохранённый ключ OpenAI повреждён. Введи его заново.") from None
