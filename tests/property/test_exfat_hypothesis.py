"""Hypothesis property-based tests for exFAT VBR and entry-set parsers."""

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.filesystems.exfat.entry import (
    ExFatFileEntrySet,
    parse_exfat_timestamp,
)
from recoverx.filesystems.exfat.vbr import ExFatVbr, calculate_exfat_vbr_checksum


@settings(max_examples=150, deadline=None)
@given(st.binary(min_size=0, max_size=1024))
def test_fuzz_exfat_vbr_from_bytes(data: bytes) -> None:
    """Fuzzing arbitrary byte streams into ExFatVbr.from_bytes must never panic."""
    try:
        vbr = ExFatVbr.from_bytes(data)
        assert vbr.bytes_per_sector in (512, 1024, 2048, 4096)
        assert vbr.cluster_count > 0
    except CorruptedBootSectorError:
        pass


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.large_base_example],
)
@given(st.binary(min_size=11 * 512, max_size=11 * 512))
def test_fuzz_exfat_vbr_checksum_invariants(vbr_bytes: bytes) -> None:
    """Checksum calculation over 11 sectors is deterministic and returns uint32."""
    chk1 = calculate_exfat_vbr_checksum(vbr_bytes, 512)
    chk2 = calculate_exfat_vbr_checksum(vbr_bytes, 512)
    assert chk1 == chk2
    assert 0 <= chk1 <= 0xFFFFFFFF


@settings(max_examples=100, deadline=None)
@given(st.lists(st.binary(min_size=32, max_size=32), min_size=0, max_size=5))
def test_fuzz_exfat_entry_set_parsing(entries: list[bytes]) -> None:
    """Fuzzing 32-byte chunks into ExFatFileEntrySet.parse_from_entries must never panic."""
    res = ExFatFileEntrySet.parse_from_entries(entries)
    if res is not None:
        assert isinstance(res.filename, str)
        assert isinstance(res.file_size, int)
        assert isinstance(res.first_cluster, int)


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=0, max_value=0xFFFFFFFF))
def test_fuzz_exfat_timestamp(ts_val: int) -> None:
    """exFAT timestamp parser returns valid ISO string or None, never crashes."""
    res = parse_exfat_timestamp(ts_val)
    if res is not None:
        assert "T" in res
        assert res.endswith("Z")
