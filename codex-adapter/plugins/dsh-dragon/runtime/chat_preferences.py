"""Persist the conversation settings with a Windows user-encrypted API key."""
from base64 import b64decode, b64encode
import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QSettings

from chat_api import completions_url


PREFERENCES = 'chat_preferences'


def read_preferences(settings):
    preferences = {
        'backend': settings.value('chat_backend', 'api', type=str),
        'codex_model': settings.value('chat_codex_model', '', type=str),
        'endpoint': settings.value('chat_endpoint', '', type=str),
        'model': settings.value('chat_model', '', type=str),
        'protected_key': '',
    }
    saved = settings.value(PREFERENCES)
    if isinstance(saved, dict):
        for name in preferences:
            if isinstance(saved.get(name), str):
                preferences[name] = saved[name]
    return preferences


def save_preferences(settings, preferences):
    previous = settings.value(PREFERENCES)
    settings.setValue(PREFERENCES, preferences)
    settings.sync()
    if settings.status() != QSettings.NoError:
        if previous is None:
            settings.remove(PREFERENCES)
        else:
            settings.setValue(PREFERENCES, previous)
        settings.sync()
        raise OSError('无法保存模型设置，请检查当前用户的设置目录权限。')


class DataBlob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def data_blob(buffer, size):
    return DataBlob(size, ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))


def crypt_data(value, endpoint, *, decrypt):
    if sys.platform != 'win32':
        raise OSError('Windows user encryption is unavailable')
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = (ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob),
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob))
    operation.restype = wintypes.BOOL
    local_free = ctypes.WinDLL('kernel32').LocalFree
    local_free.argtypes = (wintypes.HLOCAL,)
    local_free.restype = wintypes.HLOCAL

    data_buffer = ctypes.create_string_buffer(value)
    # Bind the saved key to the same completion URL used when sending it.
    purpose = b'DSHDragon chat key v1\0' + completions_url(endpoint).encode('utf8')
    purpose_buffer = ctypes.create_string_buffer(purpose)
    source = data_blob(data_buffer, len(value))
    entropy = data_blob(purpose_buffer, len(purpose))
    result = DataBlob()
    try:
        if not operation(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(result)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.memset(data_buffer, 0, len(value))
        if result.data:
            if decrypt:
                ctypes.memset(result.data, 0, result.size)
            local_free(ctypes.cast(result.data, wintypes.HLOCAL))


def save_key(key, endpoint):
    if not key:
        return ''
    try:
        return b64encode(crypt_data(key.encode('utf8'), endpoint, decrypt=False)).decode('ascii')
    except OSError as error:
        raise ValueError('Windows 无法加密保存 API Key，请检查当前用户权限后重试。') from error


def load_key(protected_key, endpoint):
    if not protected_key:
        return ''
    try:
        value = b64decode(protected_key, validate=True)
        return crypt_data(value, endpoint, decrypt=True).decode('utf8')
    except (OSError, ValueError):
        return ''
