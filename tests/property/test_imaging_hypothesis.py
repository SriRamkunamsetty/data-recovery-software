"""Hypothesis property tests for RangeStatusMap invariants."""

from hypothesis import given, settings
from hypothesis import strategies as st

from recoverx.domain.imaging import SectorStatus
from recoverx.infrastructure.storage.range_map import RangeStatusMap


@st.composite
def update_action_strategy(draw: st.DrawFn, total_sectors: int) -> tuple[int, int, SectorStatus]:
    start = draw(st.integers(min_value=0, max_value=total_sectors - 1))
    count = draw(st.integers(min_value=1, max_value=total_sectors - start))
    status = draw(st.sampled_from(list(SectorStatus)))
    return (start, count, status)


@settings(max_examples=100)
@given(
    total_sectors=st.integers(min_value=10, max_value=500),
    data=st.data(),
)
def test_range_map_invariants_under_arbitrary_updates(
    total_sectors: int, data: st.DataObject
) -> None:
    """Verify that RangeStatusMap preserves contiguous partition and coalescing invariants."""
    rmap = RangeStatusMap(total_sectors=total_sectors)

    # Perform between 1 and 20 random update operations
    num_updates = data.draw(st.integers(min_value=1, max_value=20))
    for _ in range(num_updates):
        start = data.draw(st.integers(min_value=0, max_value=total_sectors - 1))
        count = data.draw(st.integers(min_value=1, max_value=total_sectors - start))
        status = data.draw(st.sampled_from(list(SectorStatus)))
        rmap.update_range(start, count, status)

        # Invariant 1: Total sector sum must exactly equal total_sectors
        assert sum(r.sector_count for r in rmap.ranges) == total_sectors

        # Invariant 2: Ranges must be contiguous and non-overlapping
        for i in range(len(rmap.ranges) - 1):
            cur = rmap.ranges[i]
            nxt = rmap.ranges[i + 1]
            assert cur.start_sector + cur.sector_count == nxt.start_sector

            # Invariant 3: Adjacent ranges must not have identical status (coalescing)
            assert not (cur.status == nxt.status and cur.error_message == nxt.error_message)

    # Invariant 4: Round-trip serialization must be bit-for-bit identical
    serialized = rmap.to_dict()
    reconstructed = RangeStatusMap.from_dict(serialized)
    assert reconstructed.total_sectors == rmap.total_sectors
    assert reconstructed.ranges == rmap.ranges
