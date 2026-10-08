"""Windows-native credential protection and RSA signature verification.

No executable helpers, third-party cryptography packages or credential-manager
reads are needed. DPAPI binds ciphertext to the current Windows user and PC.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import hashlib
import struct
import sys

from .chatgpt_http import ChatGPTError


class _Blob(ctypes.Structure):
    _fields_ = [("size", w.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _windows_only():
    if sys.platform != "win32":
        raise ChatGPTError("platform", "ChatGPT credential protection requires Windows.")


def _dpapi(payload: bytes, *, protect: bool) -> bytes:
    _windows_only()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(payload)
    incoming = _Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy_buffer = ctypes.create_string_buffer(b"Context Palette ChatGPT credentials v1")
    entropy = _Blob(len(entropy_buffer.raw) - 1, ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = _Blob()
    if protect:
        operation = crypt.CryptProtectData
        operation.argtypes = [ctypes.POINTER(_Blob), w.LPCWSTR, ctypes.POINTER(_Blob), ctypes.c_void_p,
                              ctypes.c_void_p, w.DWORD, ctypes.POINTER(_Blob)]
        description = "Context Palette ChatGPT"
    else:
        operation = crypt.CryptUnprotectData
        operation.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                              ctypes.c_void_p, w.DWORD, ctypes.POINTER(_Blob)]
        description = None
    operation.restype = w.BOOL
    try:
        if not operation(ctypes.byref(incoming), description, ctypes.byref(entropy), None, None,
                         1, ctypes.byref(outgoing)):  # CRYPTPROTECT_UI_FORBIDDEN; current user only.
            raise ChatGPTError("credential_protection", "Windows could not protect or unlock this app's ChatGPT credentials.")
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.memset(buffer, 0, len(buffer))
        if outgoing.data:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel.LocalFree(outgoing.data)


def protect_credentials(payload: bytes) -> bytes:
    return _dpapi(payload, protect=True)


def unprotect_credentials(payload: bytes) -> bytes:
    return _dpapi(payload, protect=False)


class _PKCS1Padding(ctypes.Structure):
    _fields_ = [("algorithm", w.LPCWSTR)]


def verify_rs256(modulus: bytes, exponent: bytes, message: bytes, signature: bytes) -> bool:
    """Verify RSASSA-PKCS1-v1_5/SHA-256 with Windows CNG (not JWT decoding)."""
    _windows_only()
    if not 256 <= len(modulus) <= 1024 or not 1 <= len(exponent) <= 8 or len(signature) != len(modulus):
        return False
    if modulus[0] == 0 or int.from_bytes(exponent, "big") < 3 or int.from_bytes(exponent, "big") % 2 == 0:
        return False
    bcrypt = ctypes.WinDLL("bcrypt", use_last_error=True)
    pointer = ctypes.c_void_p
    ulong = w.ULONG
    bcrypt.BCryptOpenAlgorithmProvider.argtypes = [ctypes.POINTER(pointer), w.LPCWSTR, w.LPCWSTR, ulong]
    bcrypt.BCryptImportKeyPair.argtypes = [pointer, pointer, w.LPCWSTR, ctypes.POINTER(pointer), pointer, ulong, ulong]
    bcrypt.BCryptVerifySignature.argtypes = [pointer, pointer, pointer, ulong, pointer, ulong, ulong]
    bcrypt.BCryptDestroyKey.argtypes = [pointer]
    bcrypt.BCryptCloseAlgorithmProvider.argtypes = [pointer, ulong]
    for name in ("BCryptOpenAlgorithmProvider", "BCryptImportKeyPair", "BCryptVerifySignature",
                 "BCryptDestroyKey", "BCryptCloseAlgorithmProvider"):
        getattr(bcrypt, name).restype = ctypes.c_long
    provider, key = pointer(), pointer()
    try:
        if bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(provider), "RSA", None, 0) != 0:
            raise ChatGPTError("signature_platform", "Windows could not initialize secure ChatGPT identity verification.")
        # BCRYPT_RSAKEY_BLOB followed by big-endian exponent and modulus.
        bit_length = int.from_bytes(modulus, "big").bit_length()
        blob = struct.pack("<6I", 0x31415352, bit_length, len(exponent), len(modulus), 0, 0) + exponent + modulus
        key_blob = ctypes.create_string_buffer(blob)
        if bcrypt.BCryptImportKeyPair(provider, None, "RSAPUBLICBLOB", ctypes.byref(key), key_blob, len(blob), 0) != 0:
            return False
        digest = hashlib.sha256(message).digest()
        digest_buffer = ctypes.create_string_buffer(digest)
        signature_buffer = ctypes.create_string_buffer(signature)
        padding = _PKCS1Padding("SHA256")
        status = bcrypt.BCryptVerifySignature(key, ctypes.byref(padding), digest_buffer, len(digest),
                                             signature_buffer, len(signature), 2)  # BCRYPT_PAD_PKCS1
        if status == 0:
            return True
        if status & 0xFFFFFFFF == 0xC000A000:  # STATUS_INVALID_SIGNATURE
            return False
        raise ChatGPTError("signature_platform", "Windows could not verify this ChatGPT identity.")
    finally:
        if key.value:
            bcrypt.BCryptDestroyKey(key)
        if provider.value:
            bcrypt.BCryptCloseAlgorithmProvider(provider, 0)
