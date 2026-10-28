"""Unit tests for exFAT Allocation Bitmap reader and contiguous cluster checks."""

from pathlib import Path

from recoverx.filesystems.exfat.bitmap import ExFatAllocationBitmap
from recoverx.filesystems.exfat.vbr import ExFatVbr
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.exfat_builder import SyntheticExFatBuilder


def test_exfat_bitmap_reading_and_allocation_status(tmp_path: Path) -> None:
    """Verify bit decoding for allocated and free clusters."""
    builder = SyntheticExFatBuilder(total_sectors=32768)
    builder.add_file("active.txt", b"active data", is_deleted=False)
    builder.add_file("deleted.txt", b"deleted data", is_deleted=True)
    manifest = builder.build(tmp_path / "exfat_bmp.img")

    with DiskImageReader(manifest.image_path) as reader:
        vbr = ExFatVbr.from_reader(reader, base_offset=0)

        # Cluster 2 = root, Cluster 3 = bitmap, Cluster 4 = upcase
        bitmap = ExFatAllocationBitmap(
            reader=reader,
            vbr=vbr,
            bitmap_first_cluster=3,
            bitmap_length_bytes=512,
        )

        # System clusters are allocated (bit = 1)
        assert bitmap.is_cluster_allocated(2) is True
        assert bitmap.is_cluster_allocated(3) is True
        assert bitmap.is_cluster_allocated(4) is True

        # Active file cluster is allocated (bit = 1)
        active_file = manifest.get_file("active.txt")
        assert active_file is not None
        assert bitmap.is_cluster_allocated(active_file.first_cluster) is True
        assert bitmap.is_cluster_free(active_file.first_cluster) is False

        # Deleted file cluster is free (bit = 0)
        del_file = manifest.get_file("deleted.txt")
        assert del_file is not None
        assert bitmap.is_cluster_free(del_file.first_cluster) is True
        assert bitmap.is_cluster_allocated(del_file.first_cluster) is False


def test_exfat_bitmap_check_contiguous_chain(tmp_path: Path) -> None:
    """Verify contiguous cluster validation accurately identifies allocated clusters."""
    builder_ex = SyntheticExFatBuilder(total_sectors=32768)
    manifest = builder_ex.build(tmp_path / "bmp_chain.img")

    with DiskImageReader(manifest.image_path) as reader:
        vbr = ExFatVbr.from_reader(reader, base_offset=0)

    # Write custom bitmap byte at cluster 3 (bitmap_first_cluster):
    # Cluster 2: 1 (alloc), Cluster 3: 0 (free), Cluster 4: 0 (free), Cluster 5: 1 (alloc)
    # Byte 0: bit 0 (clus 2)=1, bit 1 (clus 3)=0, bit 2 (clus 4)=0, bit 3 (clus 5)=1 -> 0x09
    bmp_offset = vbr.cluster_to_byte_offset(3)
    with open(manifest.image_path, "r+b") as f:
        f.seek(bmp_offset)
        f.write(b"\x09")

    with DiskImageReader(manifest.image_path) as reader:
        bitmap = ExFatAllocationBitmap(
            reader=reader,
            vbr=vbr,
            bitmap_first_cluster=3,
            bitmap_length_bytes=10,
        )
        # Check clusters 3 and 4 (both free) -> True
        all_free, bad = bitmap.check_contiguous_chain(first_cluster=3, count=2)
        assert all_free is True
        assert len(bad) == 0

        # Check clusters 3, 4, 5 (cluster 5 is allocated!) -> False, bad=[5]
        all_free_3, bad_3 = bitmap.check_contiguous_chain(first_cluster=3, count=3)
        assert all_free_3 is False
        assert bad_3 == [5]
