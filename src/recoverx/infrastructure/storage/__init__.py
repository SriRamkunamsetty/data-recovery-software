"""Storage and block device infrastructure."""

from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceDisconnectedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
    StorageError,
)
from recoverx.infrastructure.storage.fault import (
    ByteRange,
    FaultConfig,
    FaultInjectionReader,
)
from recoverx.infrastructure.storage.fixtures import (
    ImageHashSnapshot,
    SyntheticFile,
    SyntheticImageBuilder,
    SyntheticImageManifest,
)
from recoverx.infrastructure.storage.image import DiskImageReader

__all__ = [
    "ByteRange",
    "DeviceClosedError",
    "DeviceDisconnectedError",
    "DeviceOutOfBoundsError",
    "DeviceReadError",
    "DiskImageReader",
    "FaultConfig",
    "FaultInjectionReader",
    "ImageHashSnapshot",
    "ReadOnlyBlockDevice",
    "StorageError",
    "SyntheticFile",
    "SyntheticImageBuilder",
    "SyntheticImageManifest",
]
