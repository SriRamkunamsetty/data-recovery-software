"""Demo mode simulation utilities for showcasing recovery workflows safely."""

import struct
from pathlib import Path

from recoverx.filesystems.fat.entry import fat_lfn_checksum


def _create_minimal_jpeg() -> bytes:
    """Generate a minimal valid JPEG image byte stream."""
    buf = bytearray()
    # SOI
    buf.extend(b"\xff\xd8")
    # APP0 (JFIF)
    buf.extend(b"\xff\xe0")
    buf.extend(struct.pack(">H", 16))
    buf.extend(b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    # DQT
    buf.extend(b"\xff\xdb")
    buf.extend(struct.pack(">H", 67))
    buf.append(0)
    buf.extend(bytes([16] * 64))
    # SOF0 (1x1 pixels)
    buf.extend(b"\xff\xc0")
    buf.extend(struct.pack(">H", 11))
    buf.append(8)
    buf.extend(struct.pack(">HH", 1, 1))
    buf.append(1)
    buf.extend(b"\x01\x11\x00")
    # DHT
    buf.extend(b"\xff\xc4")
    buf.extend(struct.pack(">H", 20))
    buf.append(0)
    buf.extend(bytes([0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))
    buf.append(0)
    # SOS
    buf.extend(b"\xff\xda")
    buf.extend(struct.pack(">H", 8))
    buf.append(1)
    buf.extend(b"\x01\x00\x00\x3f\x00")
    # Entropy data
    buf.extend(b"\x12\x34\x56\x78")
    # EOI
    buf.extend(b"\xff\xd9")
    return bytes(buf)


def create_demo_fat16_image(image_path: Path) -> Path:
    """Create a 2 MiB synthetic FAT16 disk image with deleted files for demo testing.

    Includes:
    - Deleted JPEG image (PHOTO.JPG)
    - Deleted text document (CONFIDENTIAL_NOTES.TXT)
    - Active readme (README.TXT)
    """
    total_size = 2 * 1024 * 1024  # 2 MiB
    bytes_per_sector = 512
    sectors_per_cluster = 4  # 2048 bytes per cluster
    reserved_sectors = 1
    num_fats = 2
    root_entries = 512  # 32 sectors for root dir
    sectors_per_fat = 32

    image = bytearray(total_size)

    # 1. Boot Sector (BPB)
    # Jump code
    image[0:3] = b"\xeb\x3c\x90"
    # OEM Name
    image[3:11] = b"DEMO_REC"
    # Bytes per sector
    struct.pack_into("<H", image, 11, bytes_per_sector)
    # Sectors per cluster
    image[13] = sectors_per_cluster
    # Reserved sectors
    struct.pack_into("<H", image, 14, reserved_sectors)
    # Num FATs
    image[16] = num_fats
    # Root entries
    struct.pack_into("<H", image, 17, root_entries)
    # Total sectors 16
    total_sectors = total_size // bytes_per_sector
    struct.pack_into("<H", image, 19, min(65535, total_sectors))
    # Media type (0xF8 = fixed/removable hard disk)
    image[21] = 0xF8
    # Sectors per FAT
    struct.pack_into("<H", image, 22, sectors_per_fat)
    # Sectors per track
    struct.pack_into("<H", image, 24, 32)
    # Heads
    struct.pack_into("<H", image, 26, 64)
    # Hidden sectors
    struct.pack_into("<I", image, 28, 0)
    # Total sectors 32
    struct.pack_into("<I", image, 32, 0 if total_sectors <= 65535 else total_sectors)
    # Drive number
    image[36] = 0x80
    # Boot signature
    image[38] = 0x29
    # Volume ID
    struct.pack_into("<I", image, 39, 0x12345678)
    # Volume Label
    image[43:54] = b"DEMO_DRIVE "
    # FS Type
    image[54:62] = b"FAT16   "
    # Signature
    image[510:512] = b"\x55\xaa"

    # Layout offsets
    fat1_offset = reserved_sectors * bytes_per_sector
    fat2_offset = fat1_offset + sectors_per_fat * bytes_per_sector
    root_offset = fat2_offset + sectors_per_fat * bytes_per_sector
    data_offset = root_offset + (root_entries * 32)

    cluster_size = sectors_per_cluster * bytes_per_sector

    # Initialize FATs with media descriptor
    for fat_off in (fat1_offset, fat2_offset):
        struct.pack_into("<H", image, fat_off, 0xFFF8)
        struct.pack_into("<H", image, fat_off + 2, 0xFFFF)

    # 2. Add Files
    # Cluster 2: Active README.TXT
    readme_content = (
        b"RecoverX Demonstration Simulation Disk.\r\n"
        b"This synthetic image contains deleted demo files.\r\n"
    )
    image[data_offset : data_offset + len(readme_content)] = readme_content
    # Link cluster 2 in FAT
    for fat_off in (fat1_offset, fat2_offset):
        struct.pack_into("<H", image, fat_off + 4, 0xFFFF)

    # Cluster 3: Deleted PHOTO.JPG
    jpeg_content = _create_minimal_jpeg()
    cl3_offset = data_offset + cluster_size
    image[cl3_offset : cl3_offset + len(jpeg_content)] = jpeg_content
    # Cluster 3 marked free (0x0000) in FAT because it's deleted!

    # Cluster 4: Deleted NOTES.TXT
    notes_content = (
        b"PROJECT RECOVERX FORENSIC EVIDENCE.\r\nDeleted file successfully recovered!\r\n"
    )
    cl4_offset = data_offset + 2 * cluster_size
    image[cl4_offset : cl4_offset + len(notes_content)] = notes_content
    # Cluster 4 marked free (0x0000) in FAT because it's deleted!

    # 3. Root Directory Entries
    # Entry 0: README.TXT (Active)
    # Name: README  TXT
    entry0 = root_offset
    image[entry0 : entry0 + 11] = b"README  TXT"
    image[entry0 + 11] = 0x20  # Archive
    struct.pack_into("<H", image, entry0 + 26, 2)  # First cluster 2
    struct.pack_into("<I", image, entry0 + 28, len(readme_content))

    # Entry 1: PHOTO.JPG (Deleted -> first byte 0xE5)
    entry1 = root_offset + 32
    image[entry1] = 0xE5
    image[entry1 + 1 : entry1 + 11] = b"HOTO   JPG"
    image[entry1 + 11] = 0x20
    struct.pack_into("<H", image, entry1 + 26, 3)  # First cluster 3
    struct.pack_into("<I", image, entry1 + 28, len(jpeg_content))

    # Entry 2: CONFIDENTIAL_NOTES.TXT (Deleted LFN + SFN)
    # SFN: CONFID~1.TXT (with 0xE5)
    sfn_name = b"\xe5ONFID~1TXT"
    chk = fat_lfn_checksum(sfn_name)

    # LFN Entry (0xE5 deleted)
    entry2_lfn = root_offset + 64
    image[entry2_lfn] = 0xE5  # Deleted
    image[entry2_lfn + 11] = 0x0F  # LFN attribute
    image[entry2_lfn + 12] = 0x00
    image[entry2_lfn + 13] = chk

    # SFN Entry
    entry2_sfn = root_offset + 96
    image[entry2_sfn : entry2_sfn + 11] = sfn_name
    image[entry2_sfn + 11] = 0x20
    struct.pack_into("<H", image, entry2_sfn + 26, 4)  # First cluster 4
    struct.pack_into("<I", image, entry2_sfn + 28, len(notes_content))

    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image)
    return image_path
