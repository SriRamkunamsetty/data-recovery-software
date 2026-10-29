"""Named pipe client and proxy device reader communicating with the elevated read helper."""

import ctypes
import hashlib
import logging
import sys
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.base import (
    DeviceAccessDeniedError,
    DeviceClosedError,
    DeviceDisconnectedError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)
from recoverx.infrastructure.storage.win32.api import _IS_WINDOWS, _kernel32
from recoverx.infrastructure.storage.win32.constants import (
    GENERIC_READ,
    GENERIC_WRITE,
    INVALID_HANDLE_VALUE,
    OPEN_EXISTING,
)
from recoverx.infrastructure.storage.win32.helper.protocol import HelperRequest, HelperResponse

logger = logging.getLogger(__name__)


class NamedPipeClient:
    """IPC client communicating with the elevated read helper service over a Win32 named pipe."""

    def __init__(
        self,
        pipe_name: str,
        dispatcher: Callable[[HelperRequest], HelperResponse] | None = None,
    ) -> None:
        self.pipe_name = pipe_name
        self.full_pipe_path = f"\\\\.\\pipe\\{pipe_name}"
        self._dispatcher = dispatcher
        self._pipe_handle: Any = INVALID_HANDLE_VALUE
        self._is_connected = False

    def connect(self, timeout_ms: int = 5000) -> bool:
        """Connect to the named pipe service, waiting up to timeout_ms."""
        if self._dispatcher is not None:
            self._is_connected = True
            return True

        if not _IS_WINDOWS or _kernel32 is None:
            raise OSError("Named pipe client requires Windows platform.")

        # Wait for pipe availability
        available = _kernel32.WaitNamedPipeW(self.full_pipe_path, wintypes.DWORD(timeout_ms))
        if not available:
            logger.warning("WaitNamedPipe timed out on %s", self.full_pipe_path)
            return False

        # Open pipe with Read and Write for IPC request/response exchange
        handle = _kernel32.CreateFileW(
            self.full_pipe_path,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )

        handle_val = handle if isinstance(handle, int) else getattr(handle, "value", -1)
        if handle_val in (0, INVALID_HANDLE_VALUE, -1):
            err = ctypes.get_last_error()
            logger.error("Failed to connect to pipe %s (error %d)", self.full_pipe_path, err)
            return False

        self._pipe_handle = handle_val
        self._is_connected = True
        return True

    def send_request(self, req: HelperRequest) -> HelperResponse:
        """Send a request message and receive the response message synchronously."""
        if not self._is_connected:
            raise DeviceClosedError("NamedPipeClient is not connected.")

        if self._dispatcher is not None:
            return self._dispatcher(req)

        if not _IS_WINDOWS or _kernel32 is None:
            raise OSError("Named pipe client requires Windows platform.")

        req_bytes = req.serialize()
        bytes_written = wintypes.DWORD(0)

        # Write request
        success = _kernel32.WriteFile(
            wintypes.HANDLE(self._pipe_handle),
            req_bytes,
            len(req_bytes),
            ctypes.byref(bytes_written),
            None,
        )
        if not success:
            err = ctypes.get_last_error()
            raise DeviceReadError(f"Failed to write request to helper pipe (error {err})")

        # Read response
        buf = ctypes.create_string_buffer(64 * 1024)
        bytes_read = wintypes.DWORD(0)
        success = _kernel32.ReadFile(
            wintypes.HANDLE(self._pipe_handle),
            buf,
            len(buf),
            ctypes.byref(bytes_read),
            None,
        )
        if not success or bytes_read.value == 0:
            err = ctypes.get_last_error()
            raise DeviceReadError(f"Failed to read response from helper pipe (error {err})")

        resp_raw = buf.raw[: bytes_read.value]
        return HelperResponse.deserialize(resp_raw)

    def close(self) -> None:
        """Close connection to the pipe."""
        if self._is_connected:
            self._is_connected = False
            if self._pipe_handle not in (0, INVALID_HANDLE_VALUE, -1):
                if _IS_WINDOWS and _kernel32 is not None:
                    _kernel32.CloseHandle(wintypes.HANDLE(self._pipe_handle))
                self._pipe_handle = INVALID_HANDLE_VALUE


class WindowsElevatedDeviceReader(ReadOnlyBlockDevice):
    """Read-only block device proxying I/O requests to an elevated helper process.

    Rule 1 of CLAUDE.md:
    Read-only by construction. Exposes only metadata, size_bytes,
    logical_sector_size, read_at(offset, length), and close().
    """

    def __init__(
        self,
        pipe_client: NamedPipeClient,
        device_path: str,
        physical_disk_number: int | None = None,
        owns_client: bool = False,
    ) -> None:
        self.device_path = device_path
        self._pipe_client = pipe_client
        self._owns_client = owns_client
        self._disk_number = physical_disk_number
        self._is_closed = True

        if not self._pipe_client._is_connected and not self._pipe_client.connect():
            raise DeviceAccessDeniedError(
                f"Could not connect to elevated helper pipe {pipe_client.pipe_name}. "
                "Make sure the helper service is running with administrative privileges."
            )

        # Send OPEN request
        req = HelperRequest(
            command="OPEN",
            device_path=device_path,
            disk_number=physical_disk_number,
        )
        resp = self._pipe_client.send_request(req)
        if not resp.success:
            raise DeviceAccessDeniedError(
                f"Elevated helper failed to open device {device_path}: {resp.error}"
            )

        self._handle_id = resp.handle_id
        self._size_bytes = resp.size_bytes
        self._sector_size = resp.sector_size or 512
        self._is_closed = False

        self._identity = DeviceIdentity(
            vendor=resp.vendor or "Windows",
            product=resp.product
            or (
                f"Physical Disk {physical_disk_number}"
                if physical_disk_number is not None
                else device_path
            ),
            serial=resp.serial or "",
            capacity_bytes=self._size_bytes,
            logical_sector_size=self._sector_size,
            physical_sector_size=self._sector_size,
            disk_identifier=device_path,
            sector0_hash=resp.sector0_hash,
        )

        self._device_info = StorageDevice(
            identity=self._identity,
            bus_type="USB" if "PhysicalDrive" in device_path else "Direct",
            physical_disk_number=self._disk_number,
            drive_letters=(),
            is_removable=True,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            source_path=device_path,
        )

    @property
    def identity(self) -> DeviceIdentity:
        return self._identity

    @property
    def device_info(self) -> StorageDevice:
        return self._device_info

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    @property
    def logical_sector_size(self) -> int:
        return self._sector_size

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def read_at(self, offset: int, length: int) -> bytes:
        """Proxy read request to elevated helper."""
        self.validate_bounds(offset, length)
        if length == 0:
            return b""

        req = HelperRequest(
            command="READ",
            handle_id=self._handle_id,
            offset=offset,
            length=length,
        )
        resp = self._pipe_client.send_request(req)
        if not resp.success:
            raise DeviceReadError(
                f"Elevated read error on {self.device_path} at 0x{offset:X} "
                f"({length} bytes): {resp.error}"
            )

        data = resp.get_data_bytes()
        if len(data) < length:
            logger.warning(
                "Short read via elevated helper on %s: requested %d bytes, got %d",
                self.device_path,
                length,
                len(data),
            )
        return data

    def cancel(self) -> bool:
        """Cancel ongoing I/O via elevated helper."""
        if not self._is_closed:
            req = HelperRequest(command="CANCEL", handle_id=self._handle_id)
            resp = self._pipe_client.send_request(req)
            return resp.success
        return False

    def revalidate_identity(self) -> None:
        """Revalidate device identity to detect disconnection."""
        if self._is_closed:
            raise DeviceClosedError(f"Cannot revalidate closed device {self.device_path}")

        if self._size_bytes >= self._sector_size:
            sec0 = self.read_at(0, self._sector_size)
            current_hash = hashlib.sha256(sec0).hexdigest()
            if self._identity.sector0_hash and current_hash != self._identity.sector0_hash:
                raise DeviceDisconnectedError(
                    f"Device identity mismatch on {self.device_path}! "
                    "Medium may have been swapped or removed."
                )

    def close(self) -> None:
        """Close remote handle and local proxy."""
        if not self._is_closed:
            self._is_closed = True
            try:
                req = HelperRequest(command="CLOSE", handle_id=self._handle_id)
                self._pipe_client.send_request(req)
            except Exception:
                pass
            if self._owns_client:
                self._pipe_client.close()


def launch_elevated_helper(pipe_name: str) -> bool:
    """Launch the helper process elevated via UAC verb 'runas'."""
    if not _IS_WINDOWS:
        return False

    try:
        shell32 = ctypes.windll.shell32
        if getattr(sys, "frozen", False):
            args = f"helper --pipe-name={pipe_name}"
        else:
            args = (
                f"-m recoverx.infrastructure.storage.win32.helper.service --pipe-name={pipe_name}"
            )
        sw_hide = 0
        ret = shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            args,
            None,
            sw_hide,
        )
        # ShellExecute returns > 32 on success
        return int(ret) > 32
    except Exception as exc:
        logger.error("Failed to launch elevated helper with runas: %s", exc)
        return False
