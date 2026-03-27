"""Unit tests for core/merge.py — three-way JSONL union merge."""

from __future__ import annotations

import textwrap
from pathlib import Path

import orjson
import pytest

from cwmem.core.merge import (
    MergeError,
    index_by_internal_id,
    parse_conflict_markers,
    parse_jsonl,
    resequence_public_ids,
    resolve_conflicted_jsonl,
    serialize_jsonl,
    three_way_merge,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(
    internal_id: str,
    public_id: str,
    fingerprint: str = "sha256:aaa",
    **extra: object,
) -> dict:
    return {"internal_id": internal_id, "public_id": public_id, "fingerprint": fingerprint, **extra}


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_bytes(serialize_jsonl(records))


# ---------------------------------------------------------------------------
# parse_jsonl
# ---------------------------------------------------------------------------


class TestParseJsonl:
    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        assert parse_jsonl(f) == []

    def test_missing_file(self, tmp_path: Path) -> None:
        assert parse_jsonl(tmp_path / "missing.jsonl") == []

    def test_valid_records(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        records = [_record("A", "evt-000001"), _record("B", "evt-000002")]
        _write_jsonl(f, records)
        parsed = parse_jsonl(f)
        assert len(parsed) == 2
        assert parsed[0]["internal_id"] == "A"

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.jsonl"
        f.write_text('{"internal_id":"A"}\n{BROKEN}\n')
        with pytest.raises(MergeError, match="Malformed JSON at line 2"):
            parse_jsonl(f)

    def test_missing_internal_id_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "no_id.jsonl"
        f.write_text('{"public_id":"evt-000001"}\n')
        with pytest.raises(MergeError, match="Missing 'internal_id'"):
            parse_jsonl(f)

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "blanks.jsonl"
        f.write_text('{"internal_id":"A","public_id":"e-1"}\n\n{"internal_id":"B","public_id":"e-2"}\n')
        assert len(parse_jsonl(f)) == 2


# ---------------------------------------------------------------------------
# serialize_jsonl
# ---------------------------------------------------------------------------


class TestSerializeJsonl:
    def test_empty(self) -> None:
        assert serialize_jsonl([]) == b""

    def test_sorted_keys(self) -> None:
        data = serialize_jsonl([{"z": 1, "a": 2, "internal_id": "X"}])
        obj = orjson.loads(data.strip())
        keys = list(obj.keys())
        assert keys == sorted(keys)

    def test_lf_endings(self) -> None:
        data = serialize_jsonl([_record("A", "e-1")])
        assert b"\r\n" not in data
        assert data.endswith(b"\n")


# ---------------------------------------------------------------------------
# index_by_internal_id
# ---------------------------------------------------------------------------


class TestIndex:
    def test_duplicate_raises(self) -> None:
        with pytest.raises(MergeError, match="Duplicate internal_id"):
            index_by_internal_id([_record("A", "e-1"), _record("A", "e-2")])

    def test_unique(self) -> None:
        idx = index_by_internal_id([_record("A", "e-1"), _record("B", "e-2")])
        assert set(idx) == {"A", "B"}


# ---------------------------------------------------------------------------
# Three-way merge
# ---------------------------------------------------------------------------


class TestThreeWayMerge:
    def test_no_conflicts_both_add(self) -> None:
        base = [_record("X", "evt-000001")]
        ours = [_record("X", "evt-000001"), _record("A", "evt-000002")]
        theirs = [_record("X", "evt-000001"), _record("B", "evt-000003")]
        result = three_way_merge(base, ours, theirs, "memory/events/events.jsonl")
        assert not result.conflicts
        ids = {r["internal_id"] for r in result.records}
        assert ids == {"X", "A", "B"}

    def test_public_id_collision_resequenced(self) -> None:
        base = [_record("X", "evt-000001")]
        ours = [_record("X", "evt-000001"), _record("A", "evt-000002", fingerprint="sha256:aa")]
        theirs = [_record("X", "evt-000001"), _record("B", "evt-000002", fingerprint="sha256:bb")]
        result = three_way_merge(base, ours, theirs, "memory/events/events.jsonl")
        assert not result.conflicts
        pids = {r["public_id"] for r in result.records}
        assert "evt-000002" in pids
        assert len(result.public_ids_resequenced) == 1
        old_id, new_id = result.public_ids_resequenced[0]
        assert old_id == "evt-000002"
        assert new_id == "evt-000003"

    def test_both_modified_is_conflict(self) -> None:
        base = [_record("X", "evt-000001", fingerprint="sha256:base")]
        ours = [_record("X", "evt-000001", fingerprint="sha256:ours")]
        theirs = [_record("X", "evt-000001", fingerprint="sha256:theirs")]
        result = three_way_merge(base, ours, theirs, "events.jsonl")
        assert len(result.conflicts) == 1
        assert result.conflicts[0].reason == "both_modified"

    def test_one_side_modified_auto_resolves(self) -> None:
        base = [_record("X", "evt-000001", fingerprint="sha256:base")]
        ours = [_record("X", "evt-000001", fingerprint="sha256:modified")]
        theirs = [_record("X", "evt-000001", fingerprint="sha256:base")]
        result = three_way_merge(base, ours, theirs, "events.jsonl")
        assert not result.conflicts
        assert result.records[0]["fingerprint"] == "sha256:modified"

    def test_both_modified_same_way_no_conflict(self) -> None:
        base = [_record("X", "evt-000001", fingerprint="sha256:base")]
        ours = [_record("X", "evt-000001", fingerprint="sha256:same")]
        theirs = [_record("X", "evt-000001", fingerprint="sha256:same")]
        result = three_way_merge(base, ours, theirs, "events.jsonl")
        assert not result.conflicts

    def test_modify_delete_conflict(self) -> None:
        base = [_record("X", "evt-000001", fingerprint="sha256:base")]
        ours = [_record("X", "evt-000001", fingerprint="sha256:modified")]
        theirs: list[dict] = []  # theirs deleted X
        result = three_way_merge(base, ours, theirs, "events.jsonl")
        assert len(result.conflicts) == 1
        assert result.conflicts[0].reason == "modify_delete"

    def test_delete_unmodified_no_conflict(self) -> None:
        base = [_record("X", "evt-000001", fingerprint="sha256:base")]
        ours: list[dict] = []  # ours deleted X
        theirs = [_record("X", "evt-000001", fingerprint="sha256:base")]  # theirs unchanged
        result = three_way_merge(base, ours, theirs, "events.jsonl")
        assert not result.conflicts
        # Deletion honoured — X should not be in result
        ids = {r["internal_id"] for r in result.records}
        assert "X" not in ids

    def test_empty_base_union(self) -> None:
        base: list[dict] = []
        ours = [_record("A", "evt-000001")]
        theirs = [_record("B", "evt-000002")]
        result = three_way_merge(base, ours, theirs, "events.jsonl")
        assert not result.conflicts
        ids = {r["internal_id"] for r in result.records}
        assert ids == {"A", "B"}

    def test_canonical_sort_events(self) -> None:
        base: list[dict] = []
        ours = [_record("A", "evt-000001", occurred_at="2026-03-27T10:00:00Z")]
        theirs = [_record("B", "evt-000002", occurred_at="2026-03-27T09:00:00Z")]
        result = three_way_merge(base, ours, theirs, "memory/events/events.jsonl")
        assert result.records[0]["internal_id"] == "B"  # earlier timestamp first
        assert result.records[1]["internal_id"] == "A"

    def test_canonical_sort_entries(self) -> None:
        base: list[dict] = []
        ours = [_record("A", "mem-000002")]
        theirs = [_record("B", "mem-000001")]
        result = three_way_merge(base, ours, theirs, "memory/entries/entries.jsonl")
        assert result.records[0]["public_id"] == "mem-000001"

    def test_canonical_sort_edges(self) -> None:
        base: list[dict] = []
        ours = [_record("A", "edg-000001", is_inferred=True, confidence=0.5, relation_type="b")]
        theirs = [_record("B", "edg-000002", is_inferred=False, confidence=0.9, relation_type="a")]
        result = three_way_merge(base, ours, theirs, "memory/graph/edges.jsonl")
        # is_inferred=False sorts first (0 < 1)
        assert result.records[0]["internal_id"] == "B"

    def test_idempotent(self) -> None:
        base = [_record("X", "evt-000001")]
        ours = [_record("X", "evt-000001"), _record("A", "evt-000002")]
        theirs = [_record("X", "evt-000001"), _record("B", "evt-000003")]
        r1 = three_way_merge(base, ours, theirs, "events.jsonl")
        r2 = three_way_merge(base, ours, theirs, "events.jsonl")
        assert serialize_jsonl(r1.records) == serialize_jsonl(r2.records)


# ---------------------------------------------------------------------------
# resequence_public_ids
# ---------------------------------------------------------------------------


class TestResequence:
    def test_no_collision(self) -> None:
        records = [_record("A", "evt-000001"), _record("B", "evt-000002")]
        updated, reseq = resequence_public_ids(records, {"A"})
        assert reseq == []
        assert len(updated) == 2

    def test_collision_resequences_theirs(self) -> None:
        records = [
            _record("A", "evt-000001"),
            _record("B", "evt-000001"),  # collision
        ]
        updated, reseq = resequence_public_ids(records, {"A"})
        assert len(reseq) == 1
        pids = {r["public_id"] for r in updated}
        assert "evt-000001" in pids
        assert "evt-000002" in pids


# ---------------------------------------------------------------------------
# Conflict marker parsing
# ---------------------------------------------------------------------------


class TestConflictMarkers:
    def test_standard_markers(self) -> None:
        content = textwrap.dedent("""\
            <<<<<<< HEAD
            {"internal_id":"A","public_id":"evt-000001"}
            =======
            {"internal_id":"B","public_id":"evt-000002"}
            >>>>>>> feature/x
        """)
        conflicts = parse_conflict_markers(content)
        assert len(conflicts) == 1
        ours, theirs, base = conflicts[0]
        assert any("A" in line for line in ours)
        assert any("B" in line for line in theirs)
        assert base == []

    def test_diff3_markers(self) -> None:
        content = textwrap.dedent("""\
            <<<<<<< HEAD
            {"internal_id":"A","public_id":"evt-000002"}
            ||||||| base
            {"internal_id":"X","public_id":"evt-000001"}
            =======
            {"internal_id":"B","public_id":"evt-000002"}
            >>>>>>> feature/x
        """)
        conflicts = parse_conflict_markers(content)
        assert len(conflicts) == 1
        ours, theirs, base = conflicts[0]
        assert len(base) > 0

    def test_resolve_conflicted_jsonl(self) -> None:
        content = textwrap.dedent("""\
            {"internal_id":"X","public_id":"evt-000001","fingerprint":"sha256:base"}
            <<<<<<< HEAD
            {"internal_id":"A","public_id":"evt-000002","fingerprint":"sha256:aa"}
            =======
            {"internal_id":"B","public_id":"evt-000002","fingerprint":"sha256:bb"}
            >>>>>>> feature/x
        """)
        result = resolve_conflicted_jsonl(content, "memory/events/events.jsonl")
        assert not result.conflicts
        ids = {r["internal_id"] for r in result.records}
        assert ids == {"X", "A", "B"}


# ---------------------------------------------------------------------------
# Merge driver (file-based)
# ---------------------------------------------------------------------------


class TestMergeDriver:
    def test_clean_merge(self, tmp_path: Path) -> None:
        from cwmem.core.merge import run_merge_driver

        base_f = tmp_path / "base.jsonl"
        ours_f = tmp_path / "ours.jsonl"
        theirs_f = tmp_path / "theirs.jsonl"

        base = [_record("X", "evt-000001")]
        _write_jsonl(base_f, base)
        _write_jsonl(ours_f, base + [_record("A", "evt-000002")])
        _write_jsonl(theirs_f, base + [_record("B", "evt-000003")])

        exit_code = run_merge_driver(base_f, ours_f, theirs_f, "memory/events/events.jsonl")
        assert exit_code == 0

        merged = parse_jsonl(ours_f)
        ids = {r["internal_id"] for r in merged}
        assert ids == {"X", "A", "B"}

    def test_conflict_returns_1(self, tmp_path: Path) -> None:
        from cwmem.core.merge import run_merge_driver

        base_f = tmp_path / "base.jsonl"
        ours_f = tmp_path / "ours.jsonl"
        theirs_f = tmp_path / "theirs.jsonl"

        base = [_record("X", "evt-000001", fingerprint="sha256:base")]
        _write_jsonl(base_f, base)
        _write_jsonl(ours_f, [_record("X", "evt-000001", fingerprint="sha256:ours")])
        _write_jsonl(theirs_f, [_record("X", "evt-000001", fingerprint="sha256:theirs")])

        exit_code = run_merge_driver(base_f, ours_f, theirs_f, "events.jsonl")
        assert exit_code == 1
