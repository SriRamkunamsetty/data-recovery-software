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
from recoverx.infrastructure.storage.memory import MemoryBlockDevice
from recoverx.infrastructure.storage.subdevice import SubDeviceReader

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
    "MemoryBlockDevice",
    "ReadOnlyBlockDevice",
    "StorageError",
    "SubDeviceReader",
    "SyntheticFile",
    "SyntheticImageBuilder",
    "SyntheticImageManifest",
]
