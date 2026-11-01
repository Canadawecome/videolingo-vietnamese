"""Windows Credential Manager storage; credentials never enter project files."""
import ctypes
import os
from ctypes import wintypes

TARGET = 'VideoLingoStudio/Genvoice/api.genvoice.pro'


class Credential(ctypes.Structure):
    _fields_ = [('Flags',wintypes.DWORD),('Type',wintypes.DWORD),
                ('TargetName',wintypes.LPWSTR),('Comment',wintypes.LPWSTR),
                ('LastWritten',wintypes.FILETIME),('CredentialBlobSize',wintypes.DWORD),
                ('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',wintypes.DWORD),
                ('AttributeCount',wintypes.DWORD),('Attributes',ctypes.c_void_p),
                ('TargetAlias',wintypes.LPWSTR),('UserName',wintypes.LPWSTR)]


def save_genvoice_key(key):
    if os.name != 'nt':
        raise RuntimeError('Use GENVOICE_API_KEY environment variable on this platform.')
    data = key.encode('utf-8')
    blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    credential = Credential(Type=1,TargetName=TARGET,CredentialBlobSize=len(data),
                            CredentialBlob=blob,Persist=2,UserName='VideoLingoStudio')
    api = ctypes.WinDLL('Advapi32.dll',use_last_error=True)
    api.CredWriteW.argtypes=[ctypes.POINTER(Credential),wintypes.DWORD]
    api.CredWriteW.restype=wintypes.BOOL
    if not api.CredWriteW(ctypes.byref(credential),0):
        raise RuntimeError('Could not save credential to Windows Credential Manager.')


def load_genvoice_key():
    if os.getenv('GENVOICE_API_KEY'):
        return os.environ['GENVOICE_API_KEY']
    if os.name != 'nt':
        return ''
    api = ctypes.WinDLL('Advapi32.dll',use_last_error=True)
    pointer = ctypes.POINTER(Credential)()
    api.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredReadW.restype=wintypes.BOOL
    api.CredFree.argtypes=[ctypes.c_void_p]
    if not api.CredReadW(TARGET,1,0,ctypes.byref(pointer)):
        return ''
    try:
        data=pointer.contents
        return ctypes.string_at(data.CredentialBlob,data.CredentialBlobSize).decode('utf-8')
    finally:
        api.CredFree(pointer)
