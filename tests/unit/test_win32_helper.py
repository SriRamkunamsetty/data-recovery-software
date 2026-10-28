"""Unit tests for elevated read helper protocol, service, and proxy reader."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from recoverx.infrastructure.storage.base import (
    DeviceAccessDeniedError,
    DeviceClosedError,
    DeviceOutOfBoundsError,
)
from recoverx.infrastructure.storage.win32.helper.client import (
    NamedPipeClient,
    WindowsElevatedDeviceReader,
)
from recoverx.infrastructure.storage.win32.helper.protocol import HelperRequest, HelperResponse
from recoverx.infrastructure.storage.win32.helper.service import ElevatedReadHelperService


def test_helper_protocol_serialization() -> None:
    """Test wire protocol message serialization and deserialization."""
    req = HelperRequest(command="READ", handle_id="h_123", offset=1024, length=512)
    ser = req.serialize()
    assert ser.endswith(b"\n")
    deser = HelperRequest.deserialize(ser)
    assert deser == req

    raw_data = b"FORENSIC_RAW_SECTOR_DATA"
    resp = HelperResponse(
        success=True,
        handle_id="h_123",
        size_bytes=8192,
        sector_size=512,
        data_b64="Rk9SRU5TSUNfUkFXX1NFQ1RPUl9EQVRB",
    )
    ser_resp = resp.serialize()
    deser_resp = HelperResponse.deserialize(ser_resp)
    assert deser_resp.success is True
    assert deser_resp.get_data_bytes() == raw_data


def test_elevated_read_helper_service_dispatch() -> None:
    """Test elevated helper service command dispatching and bounds rejection."""
    service = ElevatedReadHelperService(pipe_name="test_pipe")

    # 1. PING
    resp_ping = service.process_request(HelperRequest(command="PING"))
    assert resp_ping.success is True

    # 2. OPEN empty path rejected
    resp_bad_open = service.process_request(HelperRequest(command="OPEN", device_path=""))
    assert resp_bad_open.success is False
    assert "empty" in resp_bad_open.error

    # 3. Mock OPEN on valid device
    mock_reader = MagicMock()
    mock_reader.size_bytes = 4096
    mock_reader.logical_sector_size = 512
    mock_reader.identity.vendor = "SanDisk"
    mock_reader.identity.product = "Ultra"
    mock_reader.identity.serial = "ABC"
    mock_reader.identity.sector0_hash = "deadbeef"
    mock_reader.read_at.return_value = b"MOCK_SECTOR_0"

    with patch(
        "recoverx.infrastructure.storage.win32.helper.service.WindowsRawDeviceReader",
        return_value=mock_reader,
    ):
        resp_open = service.process_request(
            HelperRequest(command="OPEN", device_path=r"\\.\PhysicalDrive9", disk_number=9)
        )
        assert resp_open.success is True
        handle_id = resp_open.handle_id
        assert handle_id.startswith("h_")
        assert resp_open.size_bytes == 4096
        assert resp_open.sector_size == 512

        # 4. READ negative bounds rejected
        resp_neg = service.process_request(
            HelperRequest(command="READ", handle_id=handle_id, offset=-1, length=10)
        )
        assert resp_neg.success is False
        assert "Invalid bounds" in resp_neg.error

        # 5. READ out of bounds rejected by reader.validate_bounds
        mock_reader.validate_bounds.side_effect = DeviceOutOfBoundsError("Out of bounds")
        resp_oob = service.process_request(
            HelperRequest(command="READ", handle_id=handle_id, offset=4000, length=200)
        )
        assert resp_oob.success is False
        assert "Out of bounds" in resp_oob.error

        # 6. READ valid range
        mock_reader.validate_bounds.side_effect = None
        mock_reader.read_at.return_value = b"VALID_BYTES"
        resp_read = service.process_request(
            HelperRequest(command="READ", handle_id=handle_id, offset=0, length=11)
        )
        assert resp_read.success is True
        assert resp_read.get_data_bytes() == b"VALID_BYTES"

        # 7. CANCEL
        resp_cancel = service.process_request(HelperRequest(command="CANCEL", handle_id=handle_id))
        assert resp_cancel.success is True
        mock_reader.cancel.assert_called_once()

        # 8. CLOSE
        resp_close = service.process_request(HelperRequest(command="CLOSE", handle_id=handle_id))
        assert resp_close.success is True
        mock_reader.close.assert_called_once()

        # 9. READ after CLOSE rejected
        resp_read_after_close = service.process_request(
            HelperRequest(command="READ", handle_id=handle_id, offset=0, length=10)
        )
        assert resp_read_after_close.success is False
        assert "Invalid or closed handle" in resp_read_after_close.error

    # 10. EXIT
    resp_exit = service.process_request(HelperRequest(command="EXIT"))
    assert resp_exit.success is True
    assert service._is_running is False


def test_windows_elevated_device_reader_proxy() -> None:
    """Test WindowsElevatedDeviceReader proxying requests across NamedPipeClient."""
    service = ElevatedReadHelperService(pipe_name="proxy_test_pipe")
    client = NamedPipeClient("proxy_test_pipe", dispatcher=service.process_request)

    # Mock raw device behind helper
    mock_reader = MagicMock()
    mock_reader.size_bytes = 8192
    mock_reader.logical_sector_size = 512
    mock_reader.identity.vendor = "Kingston"
    mock_reader.identity.product = "DataTraveler"
    mock_reader.identity.serial = "SER123"
    sec0_hash = hashlib.sha256(b"\xaa" * 512).hexdigest()
    mock_reader.identity.sector0_hash = sec0_hash
    mock_reader.read_at.return_value = b"\xaa" * 512

    with patch(
        "recoverx.infrastructure.storage.win32.helper.service.WindowsRawDeviceReader",
        return_value=mock_reader,
    ):
        proxy_reader = WindowsElevatedDeviceReader(
            pipe_client=client,
            device_path=r"\\.\PhysicalDrive7",
            physical_disk_number=7,
        )

        assert proxy_reader.size_bytes == 8192
        assert proxy_reader.logical_sector_size == 512
        assert proxy_reader.identity.vendor == "Kingston"
        assert proxy_reader.identity.sector0_hash == sec0_hash
        assert proxy_reader.device_info.physical_disk_number == 7

        # Zero length read
        assert proxy_reader.read_at(0, 0) == b""

        # Read sector 0
        data = proxy_reader.read_at(0, 512)
        assert data == b"\xaa" * 512

        # Revalidation passes
        proxy_reader.revalidate_identity()

        # Cancel
        assert proxy_reader.cancel() is True

        # Close
        proxy_reader.close()
        assert proxy_reader.is_closed

        with pytest.raises(DeviceClosedError):
            proxy_reader.revalidate_identity()


def test_windows_elevated_device_reader_open_failure() -> None:
    """Test WindowsElevatedDeviceReader raises DeviceAccessDeniedError on open failure."""
    service = ElevatedReadHelperService(pipe_name="fail_test_pipe")
    client = NamedPipeClient("fail_test_pipe", dispatcher=service.process_request)

    with (
        patch(
            "recoverx.infrastructure.storage.win32.helper.service.WindowsRawDeviceReader",
            side_effect=PermissionError("Access denied opening device"),
        ),
        pytest.raises(DeviceAccessDeniedError, match="Elevated helper failed"),
    ):
        WindowsElevatedDeviceReader(
            pipe_client=client,
            device_path=r"\\.\PhysicalDrive0",
        )
