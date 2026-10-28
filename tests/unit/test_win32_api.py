"""Unit tests for Win32 API ctypes bindings and error code mapping."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from recoverx.infrastructure.storage.base import (
    DeviceAccessDeniedError,
    DeviceClosedError,
    DeviceHangError,
    DeviceReadError,
    DeviceRemovedError,
    DeviceSharingViolationError,
)
from recoverx.infrastructure.storage.win32 import api
from recoverx.infrastructure.storage.win32.api import (
    map_win32_error,
    win32_cancel_io,
    win32_close_handle,
    win32_create_file,
    win32_device_io_control,
    win32_read_file,
    win32_seek,
)
from recoverx.infrastructure.storage.win32.constants import (
    ERROR_ACCESS_DENIED,
    ERROR_DEVICE_NOT_CONNECTED,
    ERROR_INVALID_HANDLE,
    ERROR_NOT_READY,
    ERROR_OPERATION_ABORTED,
    ERROR_SHARING_VIOLATION,
    FILE_ATTRIBUTE_NORMAL,
    GENERIC_READ,
    GENERIC_WRITE,
    OPEN_EXISTING,
)


def test_map_win32_error_translations() -> None:
    """Verify Win32 system error codes map to actionable domain exceptions."""
    err_access = map_win32_error(ERROR_ACCESS_DENIED, "device")
    assert isinstance(err_access, DeviceAccessDeniedError)
    assert "administrative privileges" in str(err_access)

    err_sharing = map_win32_error(ERROR_SHARING_VIOLATION, "device")
    assert isinstance(err_sharing, DeviceSharingViolationError)
    assert "exclusive access" in str(err_sharing)

    err_disconnected = map_win32_error(ERROR_DEVICE_NOT_CONNECTED, "device")
    assert isinstance(err_disconnected, DeviceRemovedError)

    err_not_ready = map_win32_error(ERROR_NOT_READY, "device")
    assert isinstance(err_not_ready, DeviceRemovedError)

    err_handle = map_win32_error(ERROR_INVALID_HANDLE, "device")
    assert isinstance(err_handle, DeviceClosedError)

    err_abort = map_win32_error(ERROR_OPERATION_ABORTED, "device")
    assert isinstance(err_abort, DeviceHangError)

    err_unknown = map_win32_error(9999, "device")
    assert isinstance(err_unknown, DeviceReadError)
    assert "9999" in str(err_unknown)


def test_win32_create_file_strictly_forbids_write() -> None:
    """Rule 1 of CLAUDE.md: Assert ValueError is raised immediately if write flag is passed."""
    with pytest.raises(ValueError, match="FATAL SAFETY VIOLATION"):
        win32_create_file(
            path=r"\\.\PhysicalDrive0",
            desired_access=GENERIC_READ | GENERIC_WRITE,
            share_mode=0,
            creation_disposition=OPEN_EXISTING,
            flags_and_attributes=FILE_ATTRIBUTE_NORMAL,
        )


def test_win32_create_file_success() -> None:
    """Test win32_create_file returns valid handle when kernel32 succeeds."""
    mock_kernel32 = MagicMock()
    mock_kernel32.CreateFileW.return_value = 42

    with patch.object(api, "_IS_WINDOWS", True), patch.object(api, "_kernel32", mock_kernel32):
        handle = win32_create_file(
            path=r"\\.\PhysicalDrive1",
            desired_access=GENERIC_READ,
            share_mode=1,
            creation_disposition=OPEN_EXISTING,
            flags_and_attributes=FILE_ATTRIBUTE_NORMAL,
        )
        assert handle == 42
        mock_kernel32.CreateFileW.assert_called_once()


def test_win32_create_file_failure() -> None:
    """Test win32_create_file translates error code on failure (-1)."""
    mock_kernel32 = MagicMock()
    mock_kernel32.CreateFileW.return_value = -1

    with (
        patch.object(api, "_IS_WINDOWS", True),
        patch.object(api, "_kernel32", mock_kernel32),
        patch("ctypes.get_last_error", return_value=ERROR_ACCESS_DENIED),
        pytest.raises(DeviceAccessDeniedError),
    ):
        win32_create_file(
            path=r"\\.\PhysicalDrive1",
            desired_access=GENERIC_READ,
            share_mode=1,
            creation_disposition=OPEN_EXISTING,
            flags_and_attributes=FILE_ATTRIBUTE_NORMAL,
        )


def test_win32_close_handle() -> None:
    """Test win32_close_handle delegates to kernel32.CloseHandle."""
    mock_kernel32 = MagicMock()
    with patch.object(api, "_IS_WINDOWS", True), patch.object(api, "_kernel32", mock_kernel32):
        win32_close_handle(100)
        mock_kernel32.CloseHandle.assert_called_once()


def test_win32_read_file() -> None:
    """Test win32_read_file reads bytes into buffer."""
    mock_kernel32 = MagicMock()

    def fake_read_file(
        handle: Any,
        buf: Any,
        length: int,
        bytes_read_ptr: Any,
        overlapped: Any,
    ) -> bool:
        import ctypes

        payload = b"TESTING_READ_BUFFER"
        ctypes.memmove(buf, payload, len(payload))
        bytes_read_ptr.contents.value = len(payload)
        return True

    mock_kernel32.ReadFile.side_effect = fake_read_file

    with patch.object(api, "_IS_WINDOWS", True), patch.object(api, "_kernel32", mock_kernel32):
        data = win32_read_file(42, 19)
        assert data == b"TESTING_READ_BUFFER"


def test_win32_seek() -> None:
    """Test win32_seek delegates to SetFilePointerEx."""
    mock_kernel32 = MagicMock()

    def fake_seek(handle: Any, distance: Any, new_pos_ptr: Any, method: Any) -> bool:
        val = distance.value if hasattr(distance, "value") else int(distance)
        new_pos_ptr.contents.value = val
        return True

    mock_kernel32.SetFilePointerEx.side_effect = fake_seek

    with patch.object(api, "_IS_WINDOWS", True), patch.object(api, "_kernel32", mock_kernel32):
        pos = win32_seek(42, 1024)
        assert pos == 1024


def test_win32_device_io_control() -> None:
    """Test win32_device_io_control calls DeviceIoControl."""
    mock_kernel32 = MagicMock()

    def fake_ioctl(
        handle: Any,
        code: Any,
        in_buf: Any,
        in_sz: Any,
        out_buf: Any,
        out_sz: Any,
        bytes_ret_ptr: Any,
        ovlp: Any,
    ) -> bool:
        bytes_ret_ptr.contents.value = 8
        return True

    mock_kernel32.DeviceIoControl.side_effect = fake_ioctl

    with patch.object(api, "_IS_WINDOWS", True), patch.object(api, "_kernel32", mock_kernel32):
        ret = win32_device_io_control(42, 0x00070000)
        assert ret == 8


def test_win32_cancel_io() -> None:
    """Test win32_cancel_io delegates to CancelIoEx."""
    mock_kernel32 = MagicMock()
    mock_kernel32.CancelIoEx.return_value = True

    with patch.object(api, "_IS_WINDOWS", True), patch.object(api, "_kernel32", mock_kernel32):
        assert win32_cancel_io(42) is True
        mock_kernel32.CancelIoEx.assert_called_once()
