"""Synthetic partition disk image builder for MBR, GPT, and lost volume tests."""

import uuid
import zlib
from dataclasses import dataclass

from recoverx.partitions.gpt import (
    DEFAULT_ENTRY_SIZE,
    DEFAULT_NUM_ENTRIES,
    GPT_SIGNATURE,
    GPT_TYPE_WINDOWS_BASIC_DATA,
    guid_to_bytes,
)
from recoverx.partitions.mbr import (
    MBR_ENTRY_SIZE,
    MBR_SIGNATURE,
    MBR_TABLE_OFFSET,
    MBR_TYPE_EXTENDED_LBA,
    MBR_TYPE_FAT32_LBA,
    MBR_TYPE_NTFS_EXFAT,
    MBR_TYPE_PROTECTIVE_GPT,
)


@dataclass
class SyntheticPartition:
    """Specification for a partition in a synthetic disk image."""

    start_lba: int
    sector_count: int
    type_code_or_guid: str
    name: str = ""
    is_bootable: bool = False
    is_logical: bool = False
    payload_filler: bytes = b"\x00"


class SyntheticPartitionBuilder:
    """Constructs bit-perfect MBR and GPT disk images with valid and corrupted states."""

    def __init__(self, total_sectors: int = 10000, sector_size: int = 512) -> None:
        self.total_sectors = total_sectors
        self.sector_size = sector_size
        self.partitions: list[SyntheticPartition] = []
        self.disk_signature: int = 0x12345678
        self.disk_guid: str = str(uuid.uuid4())

    def add_partition(
        self,
        start_lba: int,
        sector_count: int,
        type_code_or_guid: str = "0x0C",
        name: str = "Test Partition",
        is_bootable: bool = False,
        is_logical: bool = False,
        payload_filler: bytes = b"\x55",
    ) -> "SyntheticPartitionBuilder":
        self.partitions.append(
            SyntheticPartition(
                start_lba=start_lba,
                sector_count=sector_count,
                type_code_or_guid=type_code_or_guid,
                name=name,
                is_bootable=is_bootable,
                is_logical=is_logical,
                payload_filler=payload_filler,
            )
        )
        return self

    def build_mbr_image(
        self,
        corrupt_signature: bool = False,
        corrupt_boot_indicator: bool = False,
    ) -> bytearray:
        """Build a raw disk image with a valid or corrupted MBR."""
        image = bytearray(self.total_sectors * self.sector_size)

        # Disk signature at 440..444
        image[440:444] = self.disk_signature.to_bytes(4, "little")

        # Partition entries (up to 4 primary)
        primaries = [p for p in self.partitions if not p.is_logical][:4]
        for slot, part in enumerate(primaries):
            offset = MBR_TABLE_OFFSET + (slot * MBR_ENTRY_SIZE)
            boot_ind = 0x80 if part.is_bootable else 0x00
            if corrupt_boot_indicator and slot == 0:
                boot_ind = 0x42  # Non-standard invalid boot indicator

            ptype = (
                int(part.type_code_or_guid, 0)
                if part.type_code_or_guid.startswith("0x")
                else int(part.type_code_or_guid)
            )

            image[offset] = boot_ind
            image[offset + 1 : offset + 4] = b"\x00\x02\x00"  # Dummy CHS start
            image[offset + 4] = ptype
            image[offset + 5 : offset + 8] = b"\xff\xff\xff"  # Dummy CHS end
            image[offset + 8 : offset + 12] = part.start_lba.to_bytes(4, "little")
            image[offset + 12 : offset + 16] = part.sector_count.to_bytes(4, "little")

            # Fill partition data
            part_byte_start = part.start_lba * self.sector_size
            part_byte_len = min(part.sector_count * self.sector_size, len(image) - part_byte_start)
            if part_byte_len > 0:
                image[part_byte_start : part_byte_start + part_byte_len] = (
                    part.payload_filler * ((part_byte_len // len(part.payload_filler)) + 1)
                )[:part_byte_len]

        # MBR boot signature at 510..512
        if corrupt_signature:
            image[510:512] = b"\x00\x00"
        else:
            image[510:512] = MBR_SIGNATURE

        return image

    def build_ebr_chain_image(self) -> bytearray:
        """Build an MBR disk image with an Extended Partition containing EBR chain."""
        image = bytearray(self.total_sectors * self.sector_size)
        image[440:444] = self.disk_signature.to_bytes(4, "little")
        image[510:512] = MBR_SIGNATURE

        ext_base_lba = 2000
        ext_total_count = 5000

        # Primary entry 0: extended partition
        offset = MBR_TABLE_OFFSET
        image[offset] = 0x00
        image[offset + 4] = MBR_TYPE_EXTENDED_LBA
        image[offset + 8 : offset + 12] = ext_base_lba.to_bytes(4, "little")
        image[offset + 12 : offset + 16] = ext_total_count.to_bytes(4, "little")

        # Logical partition 1 at ext_base_lba
        ebr1_offset = ext_base_lba * self.sector_size
        image[ebr1_offset + 510 : ebr1_offset + 512] = MBR_SIGNATURE
        # Entry 1 in EBR1: logical partition data
        e1 = ebr1_offset + MBR_TABLE_OFFSET
        image[e1] = 0x00
        image[e1 + 4] = MBR_TYPE_FAT32_LBA
        image[e1 + 8 : e1 + 12] = (1).to_bytes(4, "little")  # rel to EBR1
        image[e1 + 12 : e1 + 16] = (1000).to_bytes(4, "little")

        # Entry 2 in EBR1: pointer to next EBR at rel 2000 from ext_base_lba
        e2 = ebr1_offset + MBR_TABLE_OFFSET + MBR_ENTRY_SIZE
        next_rel_lba = 2000
        image[e2] = 0x00
        image[e2 + 4] = MBR_TYPE_EXTENDED_LBA
        image[e2 + 8 : e2 + 12] = next_rel_lba.to_bytes(4, "little")
        image[e2 + 12 : e2 + 16] = (1000).to_bytes(4, "little")

        # Logical partition 2 at ext_base_lba + next_rel_lba
        ebr2_lba = ext_base_lba + next_rel_lba
        ebr2_offset = ebr2_lba * self.sector_size
        image[ebr2_offset + 510 : ebr2_offset + 512] = MBR_SIGNATURE
        e2_1 = ebr2_offset + MBR_TABLE_OFFSET
        image[e2_1] = 0x00
        image[e2_1 + 4] = MBR_TYPE_NTFS_EXFAT
        image[e2_1 + 8 : e2_1 + 12] = (1).to_bytes(4, "little")
        image[e2_1 + 12 : e2_1 + 16] = (800).to_bytes(4, "little")

        return image

    def build_gpt_image(
        self,
        corrupt_primary_header_crc: bool = False,
        corrupt_primary_signature: bool = False,
        corrupt_backup_header_crc: bool = False,
        corrupt_backup_signature: bool = False,
    ) -> bytearray:
        """Build a raw disk image with Protective MBR, Primary GPT, and Backup GPT."""
        image = bytearray(self.total_sectors * self.sector_size)

        # 1. Protective MBR at LBA 0
        image[440:444] = self.disk_signature.to_bytes(4, "little")
        mbr_entry = MBR_TABLE_OFFSET
        image[mbr_entry] = 0x00  # non-bootable
        image[mbr_entry + 4] = MBR_TYPE_PROTECTIVE_GPT
        image[mbr_entry + 8 : mbr_entry + 12] = (1).to_bytes(4, "little")
        image[mbr_entry + 12 : mbr_entry + 16] = (self.total_sectors - 1).to_bytes(4, "little")
        image[510:512] = MBR_SIGNATURE

        # 2. Build Partition Entry Array (128 entries * 128 bytes)
        num_entries = DEFAULT_NUM_ENTRIES
        entry_size = DEFAULT_ENTRY_SIZE
        array_size_bytes = num_entries * entry_size
        array_sectors = (array_size_bytes + self.sector_size - 1) // self.sector_size
        part_array = bytearray(array_size_bytes)

        for i, part in enumerate(self.partitions[:num_entries]):
            offset = i * entry_size
            guid_str = (
                part.type_code_or_guid
                if "-" in part.type_code_or_guid
                else GPT_TYPE_WINDOWS_BASIC_DATA
            )
            part_array[offset : offset + 16] = guid_to_bytes(guid_str)
            part_array[offset + 16 : offset + 32] = guid_to_bytes(str(uuid.uuid4()))
            start_lba = part.start_lba
            ending_lba = part.start_lba + part.sector_count - 1
            part_array[offset + 32 : offset + 40] = start_lba.to_bytes(8, "little")
            part_array[offset + 40 : offset + 48] = ending_lba.to_bytes(8, "little")
            part_array[offset + 48 : offset + 56] = (0).to_bytes(8, "little")
            name_bytes = part.name.encode("utf-16le")[:72]
            part_array[offset + 56 : offset + 56 + len(name_bytes)] = name_bytes

        array_crc32 = zlib.crc32(part_array) & 0xFFFFFFFF

        # Primary partition array at LBA 2
        prim_array_lba = 2
        p_start = prim_array_lba * self.sector_size
        p_end = (prim_array_lba + array_sectors) * self.sector_size
        image[p_start:p_end] = part_array

        # Backup partition array at (total_sectors - 1 - array_sectors)
        backup_lba = self.total_sectors - 1
        backup_array_lba = backup_lba - array_sectors
        b_start = backup_array_lba * self.sector_size
        b_end = (backup_array_lba + array_sectors) * self.sector_size
        image[b_start:b_end] = part_array

        # 3. Primary GPT Header at LBA 1
        prim_hdr = bytearray(self.sector_size)
        prim_hdr[0:8] = b"BAD PART" if corrupt_primary_signature else GPT_SIGNATURE
        prim_hdr[8:12] = (0x00010000).to_bytes(4, "little")
        prim_hdr[12:16] = (92).to_bytes(4, "little")
        prim_hdr[24:32] = (1).to_bytes(8, "little")  # current LBA
        prim_hdr[32:40] = backup_lba.to_bytes(8, "little")  # backup LBA
        prim_hdr[40:48] = (34).to_bytes(8, "little")  # first usable LBA
        prim_hdr[48:56] = (backup_array_lba - 1).to_bytes(8, "little")  # last usable LBA
        prim_hdr[56:72] = guid_to_bytes(self.disk_guid)
        prim_hdr[72:80] = prim_array_lba.to_bytes(8, "little")
        prim_hdr[80:84] = num_entries.to_bytes(4, "little")
        prim_hdr[84:88] = entry_size.to_bytes(4, "little")
        prim_hdr[88:92] = array_crc32.to_bytes(4, "little")

        # Compute Primary Header CRC32
        prim_crc = zlib.crc32(prim_hdr[:92]) & 0xFFFFFFFF
        if corrupt_primary_header_crc:
            prim_crc = (prim_crc ^ 0xDEADBEEF) & 0xFFFFFFFF
        prim_hdr[16:20] = prim_crc.to_bytes(4, "little")
        image[1 * self.sector_size : 2 * self.sector_size] = prim_hdr

        # 4. Backup GPT Header at last LBA
        back_hdr = bytearray(self.sector_size)
        back_hdr[0:8] = b"BAD PART" if corrupt_backup_signature else GPT_SIGNATURE
        back_hdr[8:12] = (0x00010000).to_bytes(4, "little")
        back_hdr[12:16] = (92).to_bytes(4, "little")
        back_hdr[24:32] = backup_lba.to_bytes(8, "little")  # current LBA
        back_hdr[32:40] = (1).to_bytes(8, "little")  # backup LBA
        back_hdr[40:48] = (34).to_bytes(8, "little")
        back_hdr[48:56] = (backup_array_lba - 1).to_bytes(8, "little")
        back_hdr[56:72] = guid_to_bytes(self.disk_guid)
        back_hdr[72:80] = backup_array_lba.to_bytes(8, "little")
        back_hdr[80:84] = num_entries.to_bytes(4, "little")
        back_hdr[84:88] = entry_size.to_bytes(4, "little")
        back_hdr[88:92] = array_crc32.to_bytes(4, "little")

        # Compute Backup Header CRC32
        back_crc = zlib.crc32(back_hdr[:92]) & 0xFFFFFFFF
        if corrupt_backup_header_crc:
            back_crc = (back_crc ^ 0xDEADBEEF) & 0xFFFFFFFF
        back_hdr[16:20] = back_crc.to_bytes(4, "little")
        image[backup_lba * self.sector_size : (backup_lba + 1) * self.sector_size] = back_hdr

        return image

    @classmethod
    def embed_fat32_volume(
        cls,
        image: bytearray,
        start_sector: int,
        total_sectors: int,
        corrupt_primary: bool = False,
    ) -> None:
        """Embed a FAT32 boot sector and backup boot sector (sector 6) into image."""
        bpb = bytearray(512)
        bpb[0:3] = b"\xeb\x58\x90"
        bpb[3:11] = b"MSWIN4.1"
        bpb[11:13] = (512).to_bytes(2, "little")  # bytes per sector
        bpb[13] = 8  # sectors per cluster (4KB)
        bpb[14:16] = (32).to_bytes(2, "little")  # reserved sectors
        bpb[16] = 2  # num fats
        bpb[32:36] = total_sectors.to_bytes(4, "little")
        bpb[36:40] = (100).to_bytes(4, "little")  # FAT size 32
        bpb[50:52] = (6).to_bytes(2, "little")  # backup boot sector
        bpb[82:90] = b"FAT32   "
        bpb[510:512] = MBR_SIGNATURE

        # Write backup at start_sector + 6
        backup_offset = (start_sector + 6) * 512
        image[backup_offset : backup_offset + 512] = bpb

        # Write primary at start_sector
        primary_offset = start_sector * 512
        if corrupt_primary:
            image[primary_offset : primary_offset + 512] = b"\x00" * 512
        else:
            image[primary_offset : primary_offset + 512] = bpb

    @classmethod
    def embed_exfat_volume(
        cls,
        image: bytearray,
        start_sector: int,
        total_sectors: int,
        corrupt_primary: bool = False,
    ) -> None:
        """Embed an exFAT VBR and backup VBR (sector 12) into image."""
        vbr = bytearray(512)
        vbr[0:3] = b"\xeb\x76\x90"
        vbr[3:11] = b"EXFAT   "
        vbr[72:80] = total_sectors.to_bytes(8, "little")  # volume length
        vbr[108] = 9  # sector shift (512)
        vbr[109] = 3  # cluster shift (8 sectors = 4KB)
        vbr[510:512] = MBR_SIGNATURE

        # Backup VBR at start_sector + 12
        backup_offset = (start_sector + 12) * 512
        image[backup_offset : backup_offset + 512] = vbr

        # Primary VBR at start_sector
        primary_offset = start_sector * 512
        if corrupt_primary:
            image[primary_offset : primary_offset + 512] = b"\x00" * 512
        else:
            image[primary_offset : primary_offset + 512] = vbr

    @classmethod
    def embed_ntfs_volume(
        cls,
        image: bytearray,
        start_sector: int,
        total_sectors: int,
        corrupt_primary: bool = False,
    ) -> None:
        """Embed an NTFS boot sector and backup boot sector (last sector) into image."""
        boot = bytearray(512)
        boot[0:3] = b"\xeb\x52\x90"
        boot[3:11] = b"NTFS    "
        boot[11:13] = (512).to_bytes(2, "little")
        boot[13] = 8  # sectors per cluster
        boot[40:48] = total_sectors.to_bytes(8, "little")
        boot[510:512] = MBR_SIGNATURE

        # Backup at start_sector + total_sectors
        backup_offset = (start_sector + total_sectors) * 512
        if backup_offset + 512 <= len(image):
            image[backup_offset : backup_offset + 512] = boot

        # Primary at start_sector
        primary_offset = start_sector * 512
        if corrupt_primary:
            image[primary_offset : primary_offset + 512] = b"\x00" * 512
        else:
            image[primary_offset : primary_offset + 512] = boot
