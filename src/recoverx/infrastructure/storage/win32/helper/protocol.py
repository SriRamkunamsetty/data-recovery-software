"""Wire protocol messages and serializers for the elevated read helper."""

import base64
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HelperRequest:
    """Request message sent from unelevated client to elevated helper."""

    command: str  # "OPEN", "READ", "CANCEL", "CLOSE", "PING", "EXIT"
    handle_id: str = ""
    device_path: str = ""
    disk_number: int | None = None
    offset: int = 0
    length: int = 0

    def serialize(self) -> bytes:
        data = asdict(self)
        return (json.dumps(data) + "\n").encode("utf-8")

    @classmethod
    def deserialize(cls, raw_line: bytes | str) -> "HelperRequest":
        line_str = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        data = json.loads(line_str)
        return cls(**data)


@dataclass(frozen=True)
class HelperResponse:
    """Response message sent from elevated helper to unelevated client."""

    success: bool
    error: str = ""
    handle_id: str = ""
    size_bytes: int = 0
    sector_size: int = 512
    vendor: str = ""
    product: str = ""
    serial: str = ""
    sector0_hash: str = ""
    data_b64: str = ""

    def get_data_bytes(self) -> bytes:
        """Decode base64 payload into raw byte stream."""
        if self.data_b64:
            return base64.b64decode(self.data_b64.encode("ascii"))
        return b""

    def serialize(self) -> bytes:
        data = asdict(self)
        return (json.dumps(data) + "\n").encode("utf-8")

    @classmethod
    def deserialize(cls, raw_line: bytes | str) -> "HelperResponse":
        line_str = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        data = json.loads(line_str)
        return cls(**data)
