"""Unit tests for MFT record parsing, deleted record flags, and attribute priority."""

from recoverx.filesystems.ntfs.attributes import (
    NtfsFileNameAttribute,
    NtfsResidentAttribute,
)
from recoverx.filesystems.ntfs.mft_record import MftRecord


def test_mft_record_deleted_flag() -> None:
    """Test is_deleted property reflects flags & 0x0001 == 0."""
    rec_deleted = MftRecord(
        record_number=40,
        sequence_number=1,
        hard_link_count=0,
        is_in_use=False,  # Deleted
        is_directory=False,
        base_record_ref=0,
    )
    assert rec_deleted.is_deleted is True

    rec_active = MftRecord(
        record_number=41,
        sequence_number=1,
        hard_link_count=1,
        is_in_use=True,  # Active
        is_directory=False,
        base_record_ref=0,
    )
    assert rec_active.is_deleted is False


def test_mft_record_directory_flag() -> None:
    """Test is_directory property reflects directory container."""
    rec_dir = MftRecord(
        record_number=5,
        sequence_number=1,
        hard_link_count=1,
        is_in_use=True,
        is_directory=True,
        base_record_ref=0,
    )
    assert rec_dir.is_directory is True


def test_mft_record_best_file_name_priority() -> None:
    """Test Win32 namespace takes precedence over DOS 8.3 short names."""
    fn_dos = NtfsFileNameAttribute(
        parent_record_index=5,
        parent_sequence_number=1,
        creation_time=0,
        modification_time=0,
        mft_modification_time=0,
        access_time=0,
        allocated_size=4096,
        real_size=1024,
        flags=0x20,
        namespace=2,  # DOS namespace
        name="MYLONG~1.TXT",
    )
    fn_win32 = NtfsFileNameAttribute(
        parent_record_index=5,
        parent_sequence_number=1,
        creation_time=0,
        modification_time=0,
        mft_modification_time=0,
        access_time=0,
        allocated_size=4096,
        real_size=1024,
        flags=0x20,
        namespace=1,  # Win32 namespace
        name="MyLongFileName.txt",
    )

    rec = MftRecord(
        record_number=50,
        sequence_number=1,
        hard_link_count=1,
        is_in_use=False,
        is_directory=False,
        base_record_ref=0,
        file_names=[fn_dos, fn_win32],
    )

    assert rec.best_file_name is not None
    assert rec.best_file_name.name == "MyLongFileName.txt"


def test_mft_record_resident_data_size() -> None:
    """Test data_size property for resident $DATA attribute."""
    payload = b"Sample text"
    res_attr = NtfsResidentAttribute(
        attr_type=0x80,
        length=32,
        is_non_resident=False,
        name="",
        flags=0,
        attr_id=1,
        data=payload,
        value_length=len(payload),
    )
    rec = MftRecord(
        record_number=60,
        sequence_number=1,
        hard_link_count=1,
        is_in_use=True,
        is_directory=False,
        base_record_ref=0,
        attributes=[res_attr],
    )

    assert rec.data_size == len(payload)
    assert rec.data_attribute == res_attr
