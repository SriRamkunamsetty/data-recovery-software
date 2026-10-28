"""Audited Win32 ctypes function bindings and error mapping for Windows storage."""

import ctypes
import sys
from ctypes import wintypes
from typing import Any

from recoverx.infrastructure.storage.base import (
    DeviceAccessDeniedError,
    DeviceClosedError,
    DeviceHangError,
    DeviceReadError,
    DeviceRemovedError,
    DeviceSharingViolationError,
    StorageError,
)
from recoverx.infrastructure.storage.win32.constants import (
    ERROR_ACCESS_DENIED,
    ERROR_DEVICE_NOT_CONNECTED,
    ERROR_INVALID_HANDLE,
    ERROR_NOT_READY,
    ERROR_OPERATION_ABORTED,
    ERROR_SHARING_VIOLATION,
)

# On Windows, load kernel32.dll with strict signatures.
# On non-Windows platforms (e.g., Linux CI), keep references None or mockable.
_IS_WINDOWS = sys.platform == "win32"
_kernel32: Any = None

if _IS_WINDOWS:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # CreateFileW
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,  # lpFileName
        wintypes.DWORD,  # dwDesiredAccess
        wintypes.DWORD,  # dwShareMode
        ctypes.c_void_p,  # lpSecurityAttributes
        wintypes.DWORD,  # dwCreationDisposition
        wintypes.DWORD,  # dwFlagsAndAttributes
        wintypes.HANDLE,  # hTemplateFile
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE

    # CloseHandle
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    # ReadFile
    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,  # hFile
        ctypes.c_void_p,  # lpBuffer
        wintypes.DWORD,  # nNumberOfBytesToRead
        ctypes.POINTER(wintypes.DWORD),  # lpNumberOfBytesRead
        ctypes.c_void_p,  # lpOverlapped
    ]
    _kernel32.ReadFile.restype = wintypes.BOOL

    # DeviceIoControl
    _kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE,  # hDevice
        wintypes.DWORD,  # dwIoControlCode
        ctypes.c_void_p,  # lpInBuffer
        wintypes.DWORD,  # nInBufferSize
        ctypes.c_void_p,  # lpOutBuffer
        wintypes.DWORD,  # nOutBufferSize
        ctypes.POINTER(wintypes.DWORD),  # lpBytesReturned
        ctypes.c_void_p,  # lpOverlapped
    ]
    _kernel32.DeviceIoControl.restype = wintypes.BOOL

    # CancelIoEx
    _kernel32.CancelIoEx.argtypes = [
        wintypes.HANDLE,  # hFile
        ctypes.c_void_p,  # lpOverlapped
    ]
    _kernel32.CancelIoEx.restype = wintypes.BOOL

    # SetFilePointerEx
    _kernel32.SetFilePointerEx.argtypes = [
        wintypes.HANDLE,  # hFile
        ctypes.c_int64,  # liDistanceToMove
        ctypes.POINTER(ctypes.c_int64),  # lpNewFilePointer
        wintypes.DWORD,  # dwMoveMethod
    ]
    _kernel32.SetFilePointerEx.restype = wintypes.BOOL

    # Named pipe APIs
    _kernel32.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR,  # lpName
        wintypes.DWORD,  # dwOpenMode
        wintypes.DWORD,  # dwPipeMode
        wintypes.DWORD,  # nMaxInstances
        wintypes.DWORD,  # nOutBufferSize
        wintypes.DWORD,  # nInBufferSize
        wintypes.DWORD,  # nDefaultTimeOut
        ctypes.c_void_p,  # lpSecurityAttributes
    ]
    _kernel32.CreateNamedPipeW.restype = wintypes.HANDLE

    _kernel32.ConnectNamedPipe.argtypes = [
        wintypes.HANDLE,  # hNamedPipe
        ctypes.c_void_p,  # lpOverlapped
    ]
    _kernel32.ConnectNamedPipe.restype = wintypes.BOOL

    _kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
    _kernel32.DisconnectNamedPipe.restype = wintypes.BOOL

    _kernel32.WaitNamedPipeW.argtypes = [
        wintypes.LPCWSTR,  # lpNamedPipeName
        wintypes.DWORD,  # nTimeOut
    ]
    _kernel32.WaitNamedPipeW.restype = wintypes.BOOL


def map_win32_error(error_code: int, target_description: str) -> StorageError:
    """Translate Win32 error codes into specific, actionable domain StorageErrors."""
    msg = f"Win32 error {error_code} on {target_description}"
    if error_code == ERROR_ACCESS_DENIED:
        return DeviceAccessDeniedError(
            f"Access denied ({msg}). Reading physical disk devices requires administrative "
            f"privileges. Please run RecoverX elevated or use the elevated read helper."
        )
    if error_code == ERROR_SHARING_VIOLATION:
        return DeviceSharingViolationError(
            f"Sharing violation ({msg}). Another process, system service, or volume lock "
            "has exclusive access to this device. Close competing applications or dismount volumes."
        )
    if error_code in (ERROR_DEVICE_NOT_CONNECTED, ERROR_NOT_READY):
        return DeviceRemovedError(
            f"Device removed or unreachable ({msg}). Removable media was disconnected during I/O."
        )
    if error_code == ERROR_INVALID_HANDLE:
        return DeviceClosedError(f"Invalid handle ({msg}). Storage device handle is closed.")
    if error_code == ERROR_OPERATION_ABORTED:
        return DeviceHangError(
            f"Operation aborted ({msg}). The I/O request was cancelled or timed out."
        )
    return DeviceReadError(f"I/O error ({msg}). Win32 system error code: {error_code}.")


def win32_create_file(
    path: str,
    desired_access: int,
    share_mode: int,
    creation_disposition: int,
    flags_and_attributes: int,
) -> int:
    """Wrapper around CreateFileW asserting read-only access flags."""
    # Strict safety assertion (Rule 1 of CLAUDE.md)
    if desired_access & 0x40000000:  # GENERIC_WRITE bit
        raise ValueError("FATAL SAFETY VIOLATION: CreateFile requested with GENERIC_WRITE!")

    if not _IS_WINDOWS or _kernel32 is None:
        raise OSError("Win32 storage APIs are only supported on Windows hosts.")

    handle = _kernel32.CreateFileW(
        path,
        desired_access,
        share_mode,
        None,
        creation_disposition,
        flags_and_attributes,
        None,
    )

    handle_val = handle if isinstance(handle, int) else (handle.value or -1)
    if handle_val == -1:
        err = ctypes.get_last_error()
        raise map_win32_error(err, path)

    return handle_val


def win32_close_handle(handle: int) -> None:
    """Close Win32 file or device handle."""
    if _IS_WINDOWS and _kernel32 is not None and handle not in (0, -1):
        _kernel32.CloseHandle(wintypes.HANDLE(handle))


def win32_device_io_control(
    handle: int,
    io_control_code: int,
    in_buffer: Any | None = None,
    out_buffer: Any | None = None,
) -> int:
    """Send DeviceIoControl command to Win32 device handle."""
    if not _IS_WINDOWS or _kernel32 is None:
        raise OSError("Win32 storage APIs are only supported on Windows hosts.")

    in_buf_ptr = ctypes.byref(in_buffer) if in_buffer is not None else None
    in_buf_size = ctypes.sizeof(in_buffer) if in_buffer is not None else 0

    out_buf_ptr = ctypes.byref(out_buffer) if out_buffer is not None else None
    out_buf_size = ctypes.sizeof(out_buffer) if out_buffer is not None else 0

    bytes_returned = wintypes.DWORD(0)

    success = _kernel32.DeviceIoControl(
        wintypes.HANDLE(handle),
        io_control_code,
        in_buf_ptr,
        in_buf_size,
        out_buf_ptr,
        out_buf_size,
        ctypes.pointer(bytes_returned),
        None,
    )

    if not success:
        err = ctypes.get_last_error()
        raise map_win32_error(err, f"IOCTL 0x{io_control_code:08X}")

    return int(bytes_returned.value)


def win32_read_file(handle: int, length: int) -> bytes:
    """Read bytes from Win32 device handle into memory buffer."""
    if not _IS_WINDOWS or _kernel32 is None:
        raise OSError("Win32 storage APIs are only supported on Windows hosts.")

    buf = ctypes.create_string_buffer(length)
    bytes_read = wintypes.DWORD(0)

    success = _kernel32.ReadFile(
        wintypes.HANDLE(handle),
        buf,
        length,
        ctypes.pointer(bytes_read),
        None,
    )

    if not success:
        err = ctypes.get_last_error()
        raise map_win32_error(err, f"ReadFile ({length} bytes)")

    return buf.raw[: bytes_read.value]


def win32_seek(handle: int, offset: int) -> int:
    """Seek to a 64-bit byte offset on a block device."""
    if not _IS_WINDOWS or _kernel32 is None:
        raise OSError("Win32 storage APIs are only supported on Windows hosts.")

    new_pos = ctypes.c_int64(0)
    file_begin = 0
    success = _kernel32.SetFilePointerEx(
        wintypes.HANDLE(handle),
        ctypes.c_int64(offset),
        ctypes.pointer(new_pos),
        file_begin,
    )
    if not success:
        err = ctypes.get_last_error()
        raise map_win32_error(err, f"SetFilePointerEx(0x{offset:X})")

    return int(new_pos.value)


def win32_cancel_io(handle: int) -> bool:
    """Cancel pending asynchronous or hung I/O requests on a handle."""
    if not _IS_WINDOWS or _kernel32 is None:
        return False

    success = _kernel32.CancelIoEx(wintypes.HANDLE(handle), None)
    return bool(success)
