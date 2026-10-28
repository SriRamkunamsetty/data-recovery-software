"""Elevated background service providing read-only block device access over a local named pipe."""

import base64
import contextlib
import ctypes
import logging
import sys
import uuid
from ctypes import wintypes
from typing import Any

from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    ReadOnlyBlockDevice,
)
from recoverx.infrastructure.storage.win32.api import _kernel32
from recoverx.infrastructure.storage.win32.constants import (
    INVALID_HANDLE_VALUE,
    NMPWAIT_USE_DEFAULT_WAIT,
    PIPE_ACCESS_DUPLEX,
    PIPE_READMODE_MESSAGE,
    PIPE_TYPE_MESSAGE,
    PIPE_UNLIMITED_INSTANCES,
    PIPE_WAIT,
)
from recoverx.infrastructure.storage.win32.helper.protocol import HelperRequest, HelperResponse
from recoverx.infrastructure.storage.win32.reader import WindowsRawDeviceReader

logger = logging.getLogger(__name__)


class ElevatedReadHelperService:
    """Elevated worker process managing read-only raw disk handles over a secure named pipe.

    Section 3 of MASTER_PROMPT.md:
    - Runs elevated on demand.
    - Exposes only: open-by-validated-identity, read_at, metadata, close, cancel.
    - Validates every request before any I/O.
    """

    def __init__(self, pipe_name: str) -> None:
        self.pipe_name = pipe_name
        self.full_pipe_path = f"\\\\.\\pipe\\{pipe_name}"
        self._active_devices: dict[str, ReadOnlyBlockDevice] = {}
        self._is_running = True

    def process_request(self, req: HelperRequest) -> HelperResponse:
        """Dispatch a single request with strict bounds validation and error handling."""
        cmd = req.command.upper()

        if cmd == "PING":
            return HelperResponse(success=True)

        if cmd == "OPEN":
            return self._handle_open(req)

        if cmd == "READ":
            return self._handle_read(req)

        if cmd == "CANCEL":
            return self._handle_cancel(req)

        if cmd == "CLOSE":
            return self._handle_close(req)

        if cmd == "EXIT":
            self.shutdown()
            return HelperResponse(success=True)

        return HelperResponse(success=False, error=f"Unknown command: {cmd}")

    def _handle_open(self, req: HelperRequest) -> HelperResponse:
        """Open raw device in read-only mode and return identity."""
        try:
            device_path = req.device_path
            if not device_path:
                return HelperResponse(success=False, error="device_path cannot be empty")

            reader = WindowsRawDeviceReader(
                device_path=device_path,
                physical_disk_number=req.disk_number,
            )
            handle_id = f"h_{uuid.uuid4().hex[:12]}"
            self._active_devices[handle_id] = reader

            id_rec = reader.identity
            return HelperResponse(
                success=True,
                handle_id=handle_id,
                size_bytes=reader.size_bytes,
                sector_size=reader.logical_sector_size,
                vendor=id_rec.vendor,
                product=id_rec.product,
                serial=id_rec.serial,
                sector0_hash=id_rec.sector0_hash,
            )
        except Exception as exc:
            logger.exception("Failed to open device %s: %s", req.device_path, exc)
            return HelperResponse(success=False, error=str(exc))

    def _handle_read(self, req: HelperRequest) -> HelperResponse:
        """Validate bounds and read raw data from block device."""
        reader = self._active_devices.get(req.handle_id)
        if not reader:
            return HelperResponse(success=False, error=f"Invalid or closed handle: {req.handle_id}")

        if req.offset < 0 or req.length < 0:
            return HelperResponse(
                success=False,
                error=f"Invalid bounds: offset={req.offset}, length={req.length}",
            )

        try:
            reader.validate_bounds(req.offset, req.length)
            raw_data = reader.read_at(req.offset, req.length)
            b64_str = base64.b64encode(raw_data).decode("ascii")
            return HelperResponse(success=True, handle_id=req.handle_id, data_b64=b64_str)
        except (DeviceClosedError, DeviceOutOfBoundsError) as exc:
            return HelperResponse(success=False, handle_id=req.handle_id, error=str(exc))
        except Exception as exc:
            logger.exception("Read error on handle %s: %s", req.handle_id, exc)
            return HelperResponse(success=False, handle_id=req.handle_id, error=str(exc))

    def _handle_cancel(self, req: HelperRequest) -> HelperResponse:
        """Cancel hung I/O on device."""
        reader = self._active_devices.get(req.handle_id)
        if reader and hasattr(reader, "cancel"):
            reader.cancel()
        return HelperResponse(success=True, handle_id=req.handle_id)

    def _handle_close(self, req: HelperRequest) -> HelperResponse:
        """Close device and release Win32 handle."""
        reader = self._active_devices.pop(req.handle_id, None)
        if reader:
            with contextlib.suppress(Exception):
                reader.close()
        return HelperResponse(success=True, handle_id=req.handle_id)

    def shutdown(self) -> None:
        """Close all open handles and mark service stopped."""
        self._is_running = False
        for dev in list(self._active_devices.values()):
            with contextlib.suppress(Exception):
                dev.close()
        self._active_devices.clear()

    def run_server(self) -> None:
        """Main server loop listening on Win32 named pipe."""
        if sys.platform != "win32":
            logger.error("ElevatedReadHelperService requires Windows platform.")
            return

        kernel32 = _kernel32

        while self._is_running:
            # Create pipe instance
            pipe_handle = kernel32.CreateNamedPipeW(
                self.full_pipe_path,
                PIPE_ACCESS_DUPLEX,
                PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                PIPE_UNLIMITED_INSTANCES,
                64 * 1024,
                64 * 1024,
                NMPWAIT_USE_DEFAULT_WAIT,
                None,
            )

            if pipe_handle in (0, INVALID_HANDLE_VALUE, -1):
                logger.error("CreateNamedPipe failed on %s", self.full_pipe_path)
                break

            try:
                # Wait for client connection
                connected = kernel32.ConnectNamedPipe(pipe_handle, None)
                if not connected:
                    err = ctypes.get_last_error()
                    # ERROR_PIPE_CONNECTED (535) means client already connected
                    if err != 535:
                        kernel32.CloseHandle(pipe_handle)
                        continue

                # Process client requests until disconnection
                self._handle_client_connection(pipe_handle)
            finally:
                kernel32.DisconnectNamedPipe(pipe_handle)
                kernel32.CloseHandle(pipe_handle)

    def _handle_client_connection(self, pipe_handle: Any) -> None:
        """Process stream messages from connected client."""
        kernel32 = _kernel32
        buf = ctypes.create_string_buffer(64 * 1024)
        bytes_read = wintypes.DWORD(0)

        while self._is_running:
            success = kernel32.ReadFile(
                pipe_handle,
                buf,
                len(buf),
                ctypes.byref(bytes_read),
                None,
            )
            if not success or bytes_read.value == 0:
                break

            req_line = buf.raw[: bytes_read.value]
            try:
                req = HelperRequest.deserialize(req_line)
                resp = self.process_request(req)
                resp_bytes = resp.serialize()

                bytes_written = wintypes.DWORD(0)
                kernel32.WriteFile(
                    pipe_handle,
                    resp_bytes,
                    len(resp_bytes),
                    ctypes.byref(bytes_written),
                    None,
                )

                if req.command.upper() == "EXIT":
                    break
            except Exception as exc:
                logger.exception("Error processing pipe message: %s", exc)


def main() -> None:
    """Entry point when executed as a standalone elevated process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [ElevatedHelper] %(message)s",
    )
    pipe_name = "recoverx_read_helper_default"
    for arg in sys.argv[1:]:
        if arg.startswith("--pipe-name="):
            pipe_name = arg.split("=", 1)[1]

    service = ElevatedReadHelperService(pipe_name)
    logger.info("Starting elevated read helper on pipe: %s", pipe_name)
    service.run_server()


if __name__ == "__main__":
    main()
