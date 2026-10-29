"""MFT record parsing, attribute extraction, and deleted file detection."""

import struct
from dataclasses import dataclass, field

from recoverx.filesystems.ntfs.attributes import (
    AttributeType,
    NtfsAttributeHeader,
    NtfsFileNameAttribute,
    NtfsNonResidentAttribute,
    NtfsResidentAttribute,
    parse_attribute,
)
from recoverx.filesystems.ntfs.fixup import apply_fixups


@dataclass
class MftRecord:
    """Parsed MFT file record containing header metadata and attributes."""

    record_number: int
    sequence_number: int
    hard_link_count: int
    is_in_use: bool
    is_directory: bool
    base_record_ref: int
    attributes: list[NtfsAttributeHeader] = field(default_factory=list)
    file_names: list[NtfsFileNameAttribute] = field(default_factory=list)

    @property
    def is_deleted(self) -> bool:
        """True if this MFT record represents a deleted or unallocated file/directory."""
        return not self.is_in_use

    @property
    def is_base_record(self) -> bool:
        """True if this is a primary base record (not an extension record)."""
        return self.base_record_ref == 0

    @property
    def best_file_name(self) -> NtfsFileNameAttribute | None:
        """Select preferred filename, prioritizing Win32/POSIX over 8.3 short names.

        NTFS records can have multiple $FILE_NAME attributes (e.g. Win32 long name and
        DOS short name). Namespaces:
        - 1: Win32
        - 3: Win32 & DOS
        - 0: POSIX
        - 2: DOS
        """
        if not self.file_names:
            return None

        # 1. Prefer Win32 / combined Win32+DOS names
        for fn in self.file_names:
            if fn.namespace in (1, 3):
                return fn

        # 2. Prefer POSIX
        for fn in self.file_names:
            if fn.namespace == 0:
                return fn

        # 3. Fallback to DOS 8.3 or whatever is available
        return self.file_names[0]

    @property
    def data_attribute(self) -> NtfsAttributeHeader | None:
        """Find the unnamed primary $DATA attribute stream."""
        for attr in self.attributes:
            if attr.attr_type == AttributeType.DATA and attr.name == "":
                return attr
        return None

    @property
    def data_size(self) -> int:
        """Logical size of the primary unnamed data stream in bytes."""
        attr = self.data_attribute
        if attr is None:
            return 0
        if isinstance(attr, NtfsResidentAttribute):
            return attr.value_length
        if isinstance(attr, NtfsNonResidentAttribute):
            return attr.real_size
        return 0

    @classmethod
    def from_bytes(
        cls,
        raw_bytes: bytes,
        sector_size: int = 512,
        record_number: int = -1,
        max_clusters: int = 1 << 48,
    ) -> "MftRecord":
        """Parse an MFT record from raw bytes after applying update sequence fixups.

        Args:
            raw_bytes: Raw record bytes from disk (typically 1024 bytes).
            sector_size: Underlying physical sector size for fixup validation.
            record_number: Caller-provided record index or -1 to extract from header.
            max_clusters: Safety limit for data-run cluster validation.

        Returns:
            Parsed MftRecord with attributes and filenames.

        Raises:
            NtfsFixupError: If record fixup USN validation fails.
            CorruptedDirectoryError: If header offsets or attributes are malformed.
        """
        fixed = apply_fixups(raw_bytes, sector_size=sector_size)

        seq_num = struct.unpack_from("<H", fixed, 16)[0]
        link_count = struct.unpack_from("<H", fixed, 18)[0]
        first_attr_offset = struct.unpack_from("<H", fixed, 20)[0]
        flags = struct.unpack_from("<H", fixed, 22)[0]
        base_ref = struct.unpack_from("<Q", fixed, 32)[0]

        # Extract record number from header (NTFS 3.1+ offset 44) if not supplied
        rec_num = record_number
        if rec_num < 0 and len(fixed) >= 48:
            header_rec_num = struct.unpack_from("<I", fixed, 44)[0]
            rec_num = header_rec_num if header_rec_num > 0 else max(0, record_number)
        else:
            rec_num = max(0, record_number)

        is_in_use = bool(flags & 0x0001)
        is_directory = bool(flags & 0x0002)

        attributes: list[NtfsAttributeHeader] = []
        file_names: list[NtfsFileNameAttribute] = []

        curr_off = first_attr_offset
        limit_off = len(fixed)

        while curr_off < limit_off:
            attr, attr_len = parse_attribute(fixed, curr_off, max_clusters=max_clusters)
            if attr is None or attr_len <= 0:
                break

            attributes.append(attr)

            if attr.attr_type == AttributeType.FILE_NAME and isinstance(
                attr, NtfsResidentAttribute
            ):
                fn = NtfsFileNameAttribute.from_bytes(attr.data)
                if fn is not None:
                    file_names.append(fn)

            curr_off += attr_len

        return cls(
            record_number=rec_num,
            sequence_number=seq_num,
            hard_link_count=link_count,
            is_in_use=is_in_use,
            is_directory=is_directory,
            base_record_ref=base_ref,
            attributes=attributes,
            file_names=file_names,
        )
