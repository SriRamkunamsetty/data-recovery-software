"""Volume and physical disk identity resolver interface and fake implementation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice


class SeparationError(Exception):
    """Base error for device and destination separation checks."""


class DestinationOnSourceError(SeparationError):
    """Raised when destination or work directory resides on the source device or physical disk."""


class AmbiguousSeparationError(SeparationError):
    """Raised when source and destination identity cannot be determined with complete confidence."""


@dataclass(frozen=True)
class VolumeIdentity:
    """Forensic identity of a volume and its underlying physical disk."""

    volume_id: str  # Unique volume GUID or volume serial string
    physical_disk_number: int | None  # Physical drive index, e.g. 1 for PhysicalDrive1
    device_path: str = ""
    mount_point: str = ""

    def __post_init__(self) -> None:
        if not self.volume_id.strip():
            raise ValueError("volume_id cannot be empty")
        if self.physical_disk_number is not None and self.physical_disk_number < 0:
            raise ValueError("physical_disk_number must be non-negative")


class VolumeIdentityResolver(ABC):
    """Abstract resolver for volume and physical disk identities.

    CLAUDE.md Rules 2 & 3:
    Nothing the app creates goes on the source device or on any volume
    of the same physical disk. If separation cannot be established with
    confidence, refuse.
    """

    @abstractmethod
    def resolve_path(self, path: Path | str) -> VolumeIdentity:
        """Resolve a filesystem path to its volume and physical disk identity.

        Must resolve junctions, symlinks, and mapped paths to their true backing device.
        """

    @abstractmethod
    def resolve_device(self, device: ReadOnlyBlockDevice) -> VolumeIdentity:
        """Resolve a ReadOnlyBlockDevice to its volume and physical disk identity."""

    def verify_separation(
        self,
        source_device: ReadOnlyBlockDevice,
        target_path: Path | str,
        role: str = "destination",
    ) -> None:
        """Verify that target_path is physically and logically separate from source_device.

        Raises:
            DestinationOnSourceError: If target is on the same volume or same physical disk.
            AmbiguousSeparationError: If separation cannot be established with confidence.
        """
        try:
            source_ident = self.resolve_device(source_device)
            target_ident = self.resolve_path(target_path)
        except Exception as e:
            raise AmbiguousSeparationError(
                f"Cannot confidently verify source and {role} separation: {e}"
            ) from e

        # 1. Exact volume match
        if (
            source_ident.volume_id
            and target_ident.volume_id
            and source_ident.volume_id.lower() == target_ident.volume_id.lower()
        ):
            raise DestinationOnSourceError(
                f"Selected {role} resides on the SAME VOLUME ({target_ident.volume_id}) "
                f"as the source device. Operation strictly refused to prevent data loss."
            )

        # 2. Same physical disk match
        if (
            source_ident.physical_disk_number is not None
            and target_ident.physical_disk_number is not None
            and source_ident.physical_disk_number == target_ident.physical_disk_number
        ):
            raise DestinationOnSourceError(
                f"Selected {role} resides on the SAME PHYSICAL DISK "
                f"(Disk {target_ident.physical_disk_number}) as the source device. "
                f"Operation strictly refused to protect all partitions of the source disk."
            )

        # 3. If source is a physical disk but target physical disk could not be determined
        if (
            source_ident.physical_disk_number is not None
            and target_ident.physical_disk_number is None
        ):
            raise AmbiguousSeparationError(
                f"Cannot establish physical disk identity for {role} path: '{target_path}'. "
                f"Refusing operation to prevent accidental overwrite of source disk."
            )


class FakeVolumeIdentityResolver(VolumeIdentityResolver):
    """In-memory fake resolver for deterministic unit and integration testing."""

    def __init__(self) -> None:
        # Maps canonical path prefix -> VolumeIdentity
        self._path_map: dict[str, VolumeIdentity] = {}
        # Maps source device identifier -> VolumeIdentity
        self._device_map: dict[str, VolumeIdentity] = {}

    def register_path_volume(
        self,
        path_prefix: Path | str,
        volume_id: str,
        physical_disk_number: int | None,
        mount_point: str = "",
    ) -> None:
        """Register a test path prefix with a specific volume and disk identity."""
        canonical = str(Path(path_prefix).resolve()).lower()
        self._path_map[canonical] = VolumeIdentity(
            volume_id=volume_id,
            physical_disk_number=physical_disk_number,
            device_path=canonical,
            mount_point=mount_point or str(path_prefix),
        )

    def register_device_volume(
        self,
        device: ReadOnlyBlockDevice,
        volume_id: str,
        physical_disk_number: int | None,
    ) -> None:
        """Register a test device with a specific volume and disk identity."""
        ident_key = device.identity.disk_identifier or device.device_info.source_path
        self._device_map[ident_key.lower()] = VolumeIdentity(
            volume_id=volume_id,
            physical_disk_number=physical_disk_number,
            device_path=device.device_info.source_path,
        )

    def resolve_path(self, path: Path | str) -> VolumeIdentity:
        canonical = str(Path(path).resolve()).lower()
        # Find longest matching registered prefix
        best_match: VolumeIdentity | None = None
        best_len = -1
        for prefix, vol in self._path_map.items():
            matches = (
                canonical == prefix
                or canonical.startswith(prefix.rstrip("\\/") + "\\")
                or canonical.startswith(prefix.rstrip("\\/") + "/")
            )
            if matches and len(prefix) > best_len:
                best_match = vol
                best_len = len(prefix)

        if best_match is not None:
            return best_match

        # Default synthetic identity for unregistered test paths
        return VolumeIdentity(
            volume_id=f"VOL-{canonical[:12]}",
            physical_disk_number=99,  # Default safe separate disk for tests
            device_path=canonical,
        )

    def resolve_device(self, device: ReadOnlyBlockDevice) -> VolumeIdentity:
        ident_key = (device.identity.disk_identifier or device.device_info.source_path).lower()
        if ident_key in self._device_map:
            return self._device_map[ident_key]

        # Check physical disk number from StorageDevice
        disk_num = device.device_info.physical_disk_number
        return VolumeIdentity(
            volume_id=f"DEV-{device.identity.disk_identifier or 'UNKNOWN'}",
            physical_disk_number=disk_num,
            device_path=device.device_info.source_path,
        )
