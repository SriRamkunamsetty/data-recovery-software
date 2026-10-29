"""NTFS attribute headers, data run decoding, and attribute parsing."""

import struct
from dataclasses import dataclass
from enum import IntEnum

from recoverx.filesystems.base import CorruptedDirectoryError


class AttributeType(IntEnum):
    """Standard NTFS attribute type identifiers."""

    STANDARD_INFORMATION = 0x10
    ATTRIBUTE_LIST = 0x20
    FILE_NAME = 0x30
    OBJECT_ID = 0x40
    SECURITY_DESCRIPTOR = 0x50
    VOLUME_NAME = 0x60
    VOLUME_INFORMATION = 0x70
    DATA = 0x80
    INDEX_ROOT = 0x90
    INDEX_ALLOCATION = 0xA0
    BITMAP = 0xB0
    REPARSE_POINT = 0xC0
    EA_INFORMATION = 0xD0
    EA = 0xE0
    LOGGED_UTILITY_STREAM = 0x100
    END = 0xFFFFFFFF


@dataclass(frozen=True)
class DataRun:
    """Represents a contiguous cluster allocation run on an NTFS volume."""

    cluster_count: int
    lcn: int
    is_sparse: bool = False


def parse_data_runs(run_bytes: bytes, max_clusters: int = 1 << 48) -> list[DataRun]:
    """Decode NTFS compressed data run (run-list) byte stream.

    In NTFS non-resident attributes, cluster allocations are encoded as:
    - Byte 0: [Offset length in bytes (high nibble)][Cluster count length in bytes (low nibble)]
    - Followed by `count_len` bytes: unsigned cluster count
    - Followed by `offset_len` bytes: SIGNED relative cluster offset delta (LCN)
    - Terminated by byte 0x00.

    Args:
        run_bytes: Raw bytes starting at the first run-list header.
        max_clusters: Safety ceiling for volume cluster count.

    Returns:
        List of decoded DataRun objects.

    Raises:
        CorruptedDirectoryError: If run headers exceed bounds or are malformed.
    """
    runs: list[DataRun] = []
    idx = 0
    curr_lcn = 0
    max_runs = 10000

    while idx < len(run_bytes):
        if len(runs) >= max_runs:
            break

        header = run_bytes[idx]
        if header == 0x00:
            # Normal run-list termination
            break

        len_size = header & 0x0F
        off_size = (header >> 4) & 0x0F
        idx += 1

        if len_size == 0 or len_size > 8 or off_size > 8:
            raise CorruptedDirectoryError(
                f"Invalid data run header 0x{header:02x}: len_size={len_size}, off_size={off_size}"
            )

        if idx + len_size + off_size > len(run_bytes):
            raise CorruptedDirectoryError(
                f"Data run extends beyond buffer: need {len_size + off_size} B at offset {idx}"
            )

        cluster_count = int.from_bytes(run_bytes[idx : idx + len_size], "little", signed=False)
        idx += len_size

        if off_size == 0:
            # Sparse run (no clusters allocated on disk)
            runs.append(DataRun(cluster_count=cluster_count, lcn=0, is_sparse=True))
        else:
            delta_lcn = int.from_bytes(run_bytes[idx : idx + off_size], "little", signed=True)
            idx += off_size
            curr_lcn += delta_lcn

            if curr_lcn < 0 or curr_lcn >= max_clusters:
                raise CorruptedDirectoryError(
                    f"Data run LCN {curr_lcn} out of volume bounds (max {max_clusters})"
                )

            runs.append(DataRun(cluster_count=cluster_count, lcn=curr_lcn, is_sparse=False))

    return runs


@dataclass
class NtfsAttributeHeader:
    """Base class for all parsed NTFS attribute records."""

    attr_type: int
    length: int
    is_non_resident: bool
    name: str
    flags: int
    attr_id: int


@dataclass
class NtfsResidentAttribute(NtfsAttributeHeader):
    """Resident NTFS attribute whose content is stored directly inside the MFT record."""

    data: bytes
    value_length: int


@dataclass
class NtfsNonResidentAttribute(NtfsAttributeHeader):
    """Non-resident NTFS attribute whose content is allocated in clusters on disk."""

    start_vcn: int
    end_vcn: int
    allocated_size: int
    real_size: int
    initialized_size: int
    data_runs: list[DataRun]


@dataclass(frozen=True)
class NtfsFileNameAttribute:
    """Parsed $FILE_NAME (0x30) attribute content."""

    parent_record_index: int
    parent_sequence_number: int
    creation_time: int
    modification_time: int
    mft_modification_time: int
    access_time: int
    allocated_size: int
    real_size: int
    flags: int
    namespace: int
    name: str

    @classmethod
    def from_bytes(cls, data: bytes) -> "NtfsFileNameAttribute | None":
        """Parse $FILE_NAME structure from raw bytes."""
        if len(data) < 66:
            return None

        parent_ref = struct.unpack_from("<Q", data, 0)[0]
        # Lower 48 bits: MFT record index; Upper 16 bits: sequence number
        parent_record_index = parent_ref & 0x0000FFFFFFFFFFFF
        parent_seq_num = (parent_ref >> 48) & 0xFFFF

        c_time, m_time, mft_m_time, a_time = struct.unpack_from("<QQQQ", data, 8)
        alloc_size, real_size = struct.unpack_from("<QQ", data, 40)
        file_flags = struct.unpack_from("<I", data, 56)[0]
        name_len = data[64]
        namespace = data[65]

        expected_name_bytes = name_len * 2
        if 66 + expected_name_bytes > len(data):
            return None

        raw_name = data[66 : 66 + expected_name_bytes]
        filename = raw_name.decode("utf-16le", errors="replace")

        return cls(
            parent_record_index=parent_record_index,
            parent_sequence_number=parent_seq_num,
            creation_time=c_time,
            modification_time=m_time,
            mft_modification_time=mft_m_time,
            access_time=a_time,
            allocated_size=alloc_size,
            real_size=real_size,
            flags=file_flags,
            namespace=namespace,
            name=filename,
        )


def parse_attribute(
    data: bytes,
    offset: int,
    max_clusters: int = 1 << 48,
) -> tuple[NtfsAttributeHeader | None, int]:
    """Parse one attribute header and content starting at offset in data.

    Args:
        data: Fixed-up MFT record bytes.
        offset: Byte offset where attribute starts.
        max_clusters: Total clusters in volume for data run bounds checking.

    Returns:
        Tuple of (Parsed attribute or None if end/corrupted, attribute length in bytes).
    """
    if offset + 16 > len(data):
        return None, 0

    attr_type = struct.unpack_from("<I", data, offset)[0]
    if attr_type == 0xFFFFFFFF or attr_type == 0:
        # Standard end-of-attributes marker or zero padding
        return None, 0

    attr_len = struct.unpack_from("<I", data, offset + 4)[0]
    if attr_len < 16 or offset + attr_len > len(data):
        # Malformed or out-of-bounds length
        return None, 0

    is_non_res = bool(data[offset + 8])
    name_len = data[offset + 9]
    name_offset = struct.unpack_from("<H", data, offset + 10)[0]
    flags = struct.unpack_from("<H", data, offset + 12)[0]
    attr_id = struct.unpack_from("<H", data, offset + 14)[0]

    attr_name = ""
    if name_len > 0 and name_offset + (name_len * 2) <= attr_len:
        raw_name = data[offset + name_offset : offset + name_offset + (name_len * 2)]
        attr_name = raw_name.decode("utf-16le", errors="replace")

    if not is_non_res:
        # Resident attribute
        if offset + 22 > len(data):
            return None, attr_len

        val_len = struct.unpack_from("<I", data, offset + 16)[0]
        val_off = struct.unpack_from("<H", data, offset + 20)[0]

        if val_off + val_len > attr_len:
            # Resident data extends past attribute length
            val_len = max(0, attr_len - val_off)

        resident_data = data[offset + val_off : offset + val_off + val_len]
        return (
            NtfsResidentAttribute(
                attr_type=attr_type,
                length=attr_len,
                is_non_resident=False,
                name=attr_name,
                flags=flags,
                attr_id=attr_id,
                data=resident_data,
                value_length=val_len,
            ),
            attr_len,
        )

    # Non-resident attribute
    if offset + 64 > len(data):
        return None, attr_len

    start_vcn = struct.unpack_from("<Q", data, offset + 16)[0]
    end_vcn = struct.unpack_from("<Q", data, offset + 24)[0]
    run_offset = struct.unpack_from("<H", data, offset + 32)[0]
    alloc_size = struct.unpack_from("<Q", data, offset + 40)[0]
    real_size = struct.unpack_from("<Q", data, offset + 48)[0]
    init_size = struct.unpack_from("<Q", data, offset + 56)[0]

    data_runs: list[DataRun] = []
    if run_offset < attr_len:
        run_bytes = data[offset + run_offset : offset + attr_len]
        try:
            data_runs = parse_data_runs(run_bytes, max_clusters=max_clusters)
        except Exception:
            data_runs = []

    return (
        NtfsNonResidentAttribute(
            attr_type=attr_type,
            length=attr_len,
            is_non_resident=True,
            name=attr_name,
            flags=flags,
            attr_id=attr_id,
            start_vcn=start_vcn,
            end_vcn=end_vcn,
            allocated_size=alloc_size,
            real_size=real_size,
            initialized_size=init_size,
            data_runs=data_runs,
        ),
        attr_len,
    )
