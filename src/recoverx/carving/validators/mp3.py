"""MPEG Audio Layer III (MP3) file validator parsing ID3 tags and audio frame sequences."""

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

# Bitrate lookup table for MPEG1 Layer III (kbps)
BITRATES_MPEG1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
# Bitrate lookup table for MPEG2 / MPEG2.5 Layer III (kbps)
BITRATES_MPEG2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)

SAMPLERATES_MPEG1 = (44100, 48000, 32000, 0)
SAMPLERATES_MPEG2 = (22050, 24000, 16000, 0)
SAMPLERATES_MPEG25 = (11025, 12000, 8000, 0)


class Mp3Validator(FormatValidator):
    """Structural validator for MP3 files verifying ID3 metadata and MPEG frame chains."""

    @property
    def format_name(self) -> str:
        return "MP3"

    @property
    def default_extension(self) -> str:
        return "mp3"

    @property
    def magic_bytes(self) -> bytes:
        return b"ID3"

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 100 * 1024 * 1024,  # 100 MiB limit
    ) -> ValidationResult:
        """Walk ID3v2 tag and subsequent MPEG audio frame headers."""
        if header_offset < 0 or header_offset >= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Offset out of device bounds",
            )

        curr_offset = header_offset
        limit_offset = min(device.size_bytes, header_offset + max_search_bytes)

        # 1. Check ID3v2 header
        try:
            head = device.read_at(curr_offset, min(10, limit_offset - curr_offset))
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error at MP3 start",
            )

        has_id3 = False
        if len(head) >= 10 and head[:3] == b"ID3":
            has_id3 = True
            flags = head[5]
            # 4 syncsafe size bytes
            s0, s1, s2, s3 = head[6], head[7], head[8], head[9]
            if any(b >= 128 for b in (s0, s1, s2, s3)):
                return ValidationResult(
                    status=CandidateStatus.SIGNATURE_MATCHED,
                    size_bytes=10,
                    extension=self.default_extension,
                    notes="Invalid syncsafe integer in ID3v2 tag",
                )
            id3_payload_size = (s0 << 21) | (s1 << 14) | (s2 << 7) | s3
            id3_total_size = 10 + id3_payload_size
            if flags & 0x10:  # Footer present
                id3_total_size += 10

            curr_offset += id3_total_size

        # 2. Walk MPEG audio frames
        frames_walked = 0

        while curr_offset < limit_offset:
            bytes_left = limit_offset - curr_offset
            if bytes_left < 4:
                break

            try:
                frame_hdr = device.read_at(curr_offset, 4)
            except DeviceReadError:
                break

            if len(frame_hdr) < 4:
                break

            # Check for trailing ID3v1 tag (128 bytes starting with "TAG")
            if frame_hdr[:3] == b"TAG":
                curr_offset += 128
                break

            b0, b1, b2, _b3 = frame_hdr

            # Verify 11 sync bits: 0xFF followed by top 3 bits set (0xE0)
            if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
                # Frame sync lost
                break

            version_bits = (b1 >> 3) & 0x03
            layer_bits = (b1 >> 1) & 0x03
            bitrate_idx = (b2 >> 4) & 0x0F
            samplerate_idx = (b2 >> 2) & 0x03
            padding = (b2 >> 1) & 0x01

            # Version: 3=MPEG1, 2=MPEG2, 0=MPEG2.5, 1=reserved
            if version_bits == 1 or layer_bits == 0:
                break
            if bitrate_idx == 0 or bitrate_idx == 15 or samplerate_idx == 3:
                break

            # Calculate frame length
            is_mpeg1 = version_bits == 3
            if is_mpeg1:
                bitrates = BITRATES_MPEG1_L3
                samplerates = SAMPLERATES_MPEG1
            elif version_bits == 2:
                bitrates = BITRATES_MPEG2_L3
                samplerates = SAMPLERATES_MPEG2
            else:
                bitrates = BITRATES_MPEG2_L3
                samplerates = SAMPLERATES_MPEG25

            bitrate_kbps = bitrates[bitrate_idx]
            samplerate_hz = samplerates[samplerate_idx]

            if samplerate_hz == 0 or bitrate_kbps == 0:
                break

            # Frame size formula for Layer III
            if is_mpeg1:
                frame_len = (144 * bitrate_kbps * 1000) // samplerate_hz + padding
            else:
                frame_len = (72 * bitrate_kbps * 1000) // samplerate_hz + padding

            if frame_len < 4 or frame_len > 8192:
                break

            frames_walked += 1
            curr_offset += frame_len

        total_size = curr_offset - header_offset
        if frames_walked >= 5:
            tag_str = "yes" if has_id3 else "no"
            return ValidationResult(
                status=CandidateStatus.PREVIEW_VALIDATED,
                size_bytes=total_size,
                extension=self.default_extension,
                notes=f"Valid MP3 stream ({frames_walked} frames, ID3={tag_str})",
            )

        if has_id3 and frames_walked >= 1:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=total_size,
                extension=self.default_extension,
                notes=f"Truncated MP3 stream ({frames_walked} audio frames)",
            )

        return ValidationResult(
            status=CandidateStatus.SIGNATURE_MATCHED,
            size_bytes=max(total_size, 10 if has_id3 else 4),
            extension=self.default_extension,
            notes="Signature matched but insufficient audio frames",
        )
