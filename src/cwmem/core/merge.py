"""Three-way JSONL union merge for cwmem memory files.

Operates purely on JSONL dicts — no SQLite, no write lock, no Pydantic
model construction.  Used by both the automatic git merge driver and the
manual ``cwmem merge`` fallback command.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson  # noqa: I001

# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------

def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file into a list of dicts.

    Returns ``[]`` for empty files, missing files, or ``/dev/null``.
    Raises :class:`MergeError` on malformed JSON with line number context.
    """
    if not path.is_file() or path.name == "null":
        return []
    raw = path.read_bytes()
    if not raw.strip():
        return []
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(raw.split(b"\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = orjson.loads(stripped)
        except orjson.JSONDecodeError as exc:
            raise MergeError(
                f"Malformed JSON at line {lineno} in {path}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise MergeError(
                f"Expected JSON object at line {lineno} in {path}, got {type(record).__name__}"
            )
        if "internal_id" not in record:
            raise MergeError(
                f"Missing 'internal_id' at line {lineno} in {path}"
            )
        records.append(record)
    return records


def serialize_jsonl(records: list[dict[str, Any]]) -> bytes:
    """Serialize records to JSONL bytes (sorted keys, LF endings)."""
    if not records:
        return b""
    lines = [orjson.dumps(r, option=orjson.OPT_SORT_KEYS) for r in records]
    return b"\n".join(lines) + b"\n"


def index_by_internal_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build an ``internal_id`` → record lookup.

    Raises :class:`MergeError` on duplicate ``internal_id`` within a single
    file (corruption guard).
    """
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        iid = record["internal_id"]
        if iid in index:
            raise MergeError(f"Duplicate internal_id '{iid}' in the same file")
        index[iid] = record
    return index


# ---------------------------------------------------------------------------
# Merge data structures
# ---------------------------------------------------------------------------

class MergeError(Exception):
    """Raised for unrecoverable merge problems (malformed input, missing fields)."""


@dataclass(frozen=True)
class MergeConflict:
    internal_id: str
    reason: str  # "both_modified" | "modify_delete"
    ours: dict[str, Any] | None
    theirs: dict[str, Any] | None


@dataclass(frozen=True)
class MergeSets:
    base_ids: set[str]
    ours_added: list[dict[str, Any]]
    theirs_added: list[dict[str, Any]]
    ours_kept: dict[str, dict[str, Any]]
    theirs_kept: dict[str, dict[str, Any]]
    ours_deleted: set[str]
    theirs_deleted: set[str]


@dataclass(frozen=True)
class MergeResult:
    records: list[dict[str, Any]]
    public_ids_resequenced: list[tuple[str, str]] = field(default_factory=list)
    records_from_ours: int = 0
    records_from_theirs: int = 0
    conflicts: list[MergeConflict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Three-way set computation
# ---------------------------------------------------------------------------

def compute_merge_sets(
    base: list[dict[str, Any]],
    ours: list[dict[str, Any]],
    theirs: list[dict[str, Any]],
) -> MergeSets:
    base_index = index_by_internal_id(base)
    ours_index = index_by_internal_id(ours)
    theirs_index = index_by_internal_id(theirs)

    base_ids = set(base_index)
    ours_ids = set(ours_index)
    theirs_ids = set(theirs_index)

    return MergeSets(
        base_ids=base_ids,
        ours_added=[ours_index[iid] for iid in ours_ids - base_ids],
        theirs_added=[theirs_index[iid] for iid in theirs_ids - base_ids],
        ours_kept={iid: ours_index[iid] for iid in ours_ids & base_ids},
        theirs_kept={iid: theirs_index[iid] for iid in theirs_ids & base_ids},
        ours_deleted=base_ids - ours_ids,
        theirs_deleted=base_ids - theirs_ids,
    )


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def detect_conflicts(
    sets: MergeSets,
    base_index: dict[str, dict[str, Any]],
) -> list[MergeConflict]:
    conflicts: list[MergeConflict] = []

    # Records kept on both sides — check for divergent modifications
    shared_kept = set(sets.ours_kept) & set(sets.theirs_kept)
    for iid in sorted(shared_kept):
        base_fp = base_index[iid].get("fingerprint")
        ours_fp = sets.ours_kept[iid].get("fingerprint")
        theirs_fp = sets.theirs_kept[iid].get("fingerprint")

        ours_changed = ours_fp != base_fp
        theirs_changed = theirs_fp != base_fp

        if ours_changed and theirs_changed and ours_fp != theirs_fp:
            conflicts.append(MergeConflict(
                internal_id=iid,
                reason="both_modified",
                ours=sets.ours_kept[iid],
                theirs=sets.theirs_kept[iid],
            ))

    # Modify/delete conflicts
    for iid in sorted(sets.ours_deleted):
        if iid in sets.theirs_kept:
            theirs_fp = sets.theirs_kept[iid].get("fingerprint")
            base_fp = base_index[iid].get("fingerprint")
            if theirs_fp != base_fp:
                conflicts.append(MergeConflict(
                    internal_id=iid,
                    reason="modify_delete",
                    ours=None,
                    theirs=sets.theirs_kept[iid],
                ))

    for iid in sorted(sets.theirs_deleted):
        if iid in sets.ours_kept:
            ours_fp = sets.ours_kept[iid].get("fingerprint")
            base_fp = base_index[iid].get("fingerprint")
            if ours_fp != base_fp:
                conflicts.append(MergeConflict(
                    internal_id=iid,
                    reason="modify_delete",
                    ours=sets.ours_kept[iid],
                    theirs=None,
                ))

    return conflicts


# ---------------------------------------------------------------------------
# Public ID re-sequencing
# ---------------------------------------------------------------------------

_PUBLIC_ID_RE = re.compile(r"^([a-z]+)-(\d+)$")


def _parse_public_id(pid: str) -> tuple[str, int] | None:
    m = _PUBLIC_ID_RE.match(pid)
    if m:
        return m.group(1), int(m.group(2))
    return None


def resequence_public_ids(
    records: list[dict[str, Any]],
    ours_internal_ids: set[str],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Fix public_id collisions: keep ours, re-assign theirs."""
    # Group records by public_id
    by_public: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        pid = r.get("public_id", "")
        by_public.setdefault(pid, []).append(r)

    # Find the max sequence number per prefix
    max_seq: dict[str, int] = {}
    for r in records:
        parsed = _parse_public_id(r.get("public_id", ""))
        if parsed:
            prefix, seq = parsed
            max_seq[prefix] = max(max_seq.get(prefix, 0), seq)

    resequenced: list[tuple[str, str]] = []
    updated_records: list[dict[str, Any]] = []

    for pid, group in by_public.items():
        if len(group) <= 1:
            updated_records.extend(group)
            continue

        # Collision — keep ours, re-assign theirs
        for r in group:
            if r["internal_id"] in ours_internal_ids:
                updated_records.append(r)
            else:
                parsed = _parse_public_id(pid)
                if parsed:
                    prefix, _ = parsed
                    next_seq = max_seq.get(prefix, 0) + 1
                    max_seq[prefix] = next_seq
                    new_pid = f"{prefix}-{next_seq:06d}"
                    old_pid = r.get("public_id", "")
                    resequenced.append((old_pid, new_pid))
                    r = {**r, "public_id": new_pid}
                updated_records.append(r)

    return updated_records, resequenced


# ---------------------------------------------------------------------------
# Canonical sort orders (match core/export.py)
# ---------------------------------------------------------------------------

def _sort_key_for_file(file_path: str, record: dict[str, Any]) -> tuple[Any, ...]:
    basename = Path(file_path).name

    if basename == "events.jsonl":
        return (record.get("occurred_at", ""), record.get("public_id", ""))
    if basename == "entries.jsonl":
        return (record.get("public_id", ""),)
    if basename == "nodes.jsonl":
        return (record.get("public_id", ""),)
    if basename == "edges.jsonl":
        is_inferred = 1 if record.get("is_inferred", False) else 0
        confidence = -float(record.get("confidence", 0))
        rel = record.get("relation_type", "")
        pid = record.get("public_id", "")
        return (is_inferred, confidence, rel, pid)
    # Fallback: sort by public_id
    return (record.get("public_id", ""),)


# ---------------------------------------------------------------------------
# Union merge
# ---------------------------------------------------------------------------

def union_merge(
    sets: MergeSets,
    base_index: dict[str, dict[str, Any]],
    file_path: str,
) -> MergeResult:
    """Perform the three-way union merge.

    Precondition: :func:`detect_conflicts` returned no conflicts.
    """
    merged: list[dict[str, Any]] = []
    from_ours = 0
    from_theirs = 0

    # 1. Kept records (present in base and at least one side)
    all_kept_ids = set(sets.ours_kept) | set(sets.theirs_kept)
    for iid in all_kept_ids:
        if iid in sets.ours_deleted:
            # Theirs kept, ours deleted — if theirs unchanged, honour deletion
            theirs_fp = sets.theirs_kept[iid].get("fingerprint")
            base_fp = base_index[iid].get("fingerprint")
            if theirs_fp == base_fp:
                continue  # Both sides effectively agree: no change needed or deleted
            # Theirs modified — this should have been caught as modify_delete conflict
            continue  # pragma: no cover
        if iid in sets.theirs_deleted:
            ours_fp = sets.ours_kept[iid].get("fingerprint")
            base_fp = base_index[iid].get("fingerprint")
            if ours_fp == base_fp:
                continue
            continue  # pragma: no cover

        # Both kept — take modified version if one changed
        ours_r = sets.ours_kept.get(iid)
        theirs_r = sets.theirs_kept.get(iid)
        base_fp = base_index[iid].get("fingerprint")

        if ours_r and theirs_r:
            ours_fp = ours_r.get("fingerprint")
            theirs_fp = theirs_r.get("fingerprint")
            if ours_fp != base_fp:
                merged.append(ours_r)
                from_ours += 1
            elif theirs_fp != base_fp:
                merged.append(theirs_r)
                from_theirs += 1
            else:
                merged.append(ours_r)  # Both match base, take either
                from_ours += 1
        elif ours_r:
            merged.append(ours_r)
            from_ours += 1
        elif theirs_r:
            merged.append(theirs_r)
            from_theirs += 1

    # 2. Added records — deduplicate by internal_id when the same
    #    record was added on both sides (common when .cwmem/ DB leaks
    #    across branches because it is gitignored).
    ours_added_ids: set[str] = set()
    for r in sets.ours_added:
        merged.append(r)
        ours_added_ids.add(r["internal_id"])
        from_ours += 1
    for r in sets.theirs_added:
        if r["internal_id"] in ours_added_ids:
            continue  # Already included from ours
        merged.append(r)
        from_theirs += 1

    # 3. Re-sequence public_id collisions
    ours_internal_ids = {r["internal_id"] for r in sets.ours_added} | set(sets.ours_kept)
    merged, resequenced = resequence_public_ids(merged, ours_internal_ids)

    # 4. Sort by canonical order
    merged.sort(key=lambda r: _sort_key_for_file(file_path, r))

    return MergeResult(
        records=merged,
        public_ids_resequenced=resequenced,
        records_from_ours=from_ours,
        records_from_theirs=from_theirs,
    )


# ---------------------------------------------------------------------------
# Full three-way merge (convenience entry point)
# ---------------------------------------------------------------------------

def three_way_merge(
    base: list[dict[str, Any]],
    ours: list[dict[str, Any]],
    theirs: list[dict[str, Any]],
    file_path: str,
) -> MergeResult:
    """Run the full three-way merge pipeline.

    Returns a :class:`MergeResult`.  If ``result.conflicts`` is non-empty
    the merge cannot be resolved automatically.
    """
    sets = compute_merge_sets(base, ours, theirs)
    base_index = index_by_internal_id(base)
    conflicts = detect_conflicts(sets, base_index)

    if conflicts:
        return MergeResult(
            records=[],
            conflicts=conflicts,
        )

    return union_merge(sets, base_index, file_path)


# ---------------------------------------------------------------------------
# Conflict marker parsing (for cwmem merge fallback)
# ---------------------------------------------------------------------------

_MARKER_OURS_START = re.compile(r"^<{7}\s")
_MARKER_BASE_START = re.compile(r"^\|{7}\s")
_MARKER_SEPARATOR = re.compile(r"^={7}$")
_MARKER_THEIRS_END = re.compile(r"^>{7}\s")


def parse_conflict_markers(
    content: str,
) -> list[tuple[list[str], list[str], list[str]]]:
    """Parse git conflict markers from file content.

    Returns a list of (ours_lines, theirs_lines, base_lines) tuples.
    ``base_lines`` is empty if diff3 markers are not present.

    Non-conflicted lines are included in both ours and theirs identically.
    """
    conflicts: list[tuple[list[str], list[str], list[str]]] = []
    lines = content.split("\n")

    ours_lines: list[str] = []
    theirs_lines: list[str] = []
    base_lines: list[str] = []
    in_conflict = False
    section = ""  # "ours" | "base" | "theirs"
    # Accumulate non-conflict lines
    preamble: list[str] = []

    for line in lines:
        if _MARKER_OURS_START.match(line):
            in_conflict = True
            section = "ours"
            ours_lines = []
            theirs_lines = []
            base_lines = []
            continue

        if in_conflict and _MARKER_BASE_START.match(line):
            section = "base"
            continue

        if in_conflict and _MARKER_SEPARATOR.match(line):
            section = "theirs"
            continue

        if in_conflict and _MARKER_THEIRS_END.match(line):
            in_conflict = False
            section = ""
            conflicts.append((ours_lines, theirs_lines, base_lines))
            ours_lines = []
            theirs_lines = []
            base_lines = []
            continue

        if in_conflict:
            if section == "ours":
                ours_lines.append(line)
            elif section == "base":
                base_lines.append(line)
            elif section == "theirs":
                theirs_lines.append(line)
        else:
            preamble.append(line)

    return conflicts


def resolve_conflicted_jsonl(
    content: str,
    file_path: str,
) -> MergeResult:
    """Parse conflict markers from a JSONL file and resolve via union merge.

    For files with conflict markers that weren't handled by the merge driver.
    """
    conflict_regions = parse_conflict_markers(content)

    if not conflict_regions:
        raise MergeError(f"No conflict markers found in {file_path}")

    # Collect all records from all conflict regions
    all_ours: list[dict[str, Any]] = []
    all_theirs: list[dict[str, Any]] = []
    all_base: list[dict[str, Any]] = []

    # Also collect non-conflicted lines (before first conflict marker)
    clean_lines = []
    for line in content.split("\n"):
        if _MARKER_OURS_START.match(line):
            break
        stripped = line.strip()
        if stripped:
            clean_lines.append(stripped)

    # Parse the clean (non-conflicted) prefix as common records
    common_records: list[dict[str, Any]] = []
    for line_text in clean_lines:
        try:
            record = orjson.loads(line_text)
            if isinstance(record, dict) and "internal_id" in record:
                common_records.append(record)
        except orjson.JSONDecodeError:
            pass

    for ours_lines, theirs_lines, base_lines in conflict_regions:
        for line_text in ours_lines:
            stripped = line_text.strip()
            if not stripped:
                continue
            try:
                record = orjson.loads(stripped)
                if isinstance(record, dict) and "internal_id" in record:
                    all_ours.append(record)
            except orjson.JSONDecodeError:
                pass

        for line_text in theirs_lines:
            stripped = line_text.strip()
            if not stripped:
                continue
            try:
                record = orjson.loads(stripped)
                if isinstance(record, dict) and "internal_id" in record:
                    all_theirs.append(record)
            except orjson.JSONDecodeError:
                pass

        for line_text in base_lines:
            stripped = line_text.strip()
            if not stripped:
                continue
            try:
                record = orjson.loads(stripped)
                if isinstance(record, dict) and "internal_id" in record:
                    all_base.append(record)
            except orjson.JSONDecodeError:
                pass

    # Build full record sets: common + conflict-specific
    full_ours = common_records + all_ours
    full_theirs = common_records + all_theirs

    # If no base from diff3 markers, infer base as common records
    # (records that appear in both ours and theirs with same internal_id and fingerprint)
    if not all_base:
        full_base = list(common_records)
    else:
        full_base = common_records + all_base

    return three_way_merge(full_base, full_ours, full_theirs, file_path)


# ---------------------------------------------------------------------------
# Git merge driver entry point
# ---------------------------------------------------------------------------

def run_merge_driver(
    base_path: Path,
    ours_path: Path,
    theirs_path: Path,
    file_path: str,
) -> int:
    """Execute the merge driver protocol.

    Returns 0 on success (merged result written to *ours_path*) or 1 on
    unresolvable conflict.
    """
    try:
        base = parse_jsonl(base_path)
        ours = parse_jsonl(ours_path)
        theirs = parse_jsonl(theirs_path)
    except MergeError as exc:
        print(f"cwmem merge-driver: {exc}", file=sys.stderr)
        return 1

    result = three_way_merge(base, ours, theirs, file_path)

    if result.conflicts:
        for c in result.conflicts:
            print(
                f"cwmem merge-driver: conflict on {c.internal_id} ({c.reason})",
                file=sys.stderr,
            )
        return 1

    output = serialize_jsonl(result.records)
    ours_path.write_bytes(output)

    reseq_msg = ""
    if result.public_ids_resequenced:
        reseq_msg = f", {len(result.public_ids_resequenced)} resequenced"
    total = result.records_from_ours + result.records_from_theirs
    print(
        f"cwmem: merged {total} records ({result.records_from_ours} ours, "
        f"{result.records_from_theirs} theirs{reseq_msg}) in {file_path}",
        file=sys.stderr,
    )
    return 0
