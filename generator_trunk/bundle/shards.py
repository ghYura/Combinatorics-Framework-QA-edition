# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""STEP 32 — launcher-side reader for ShardSink compressed-shard containers.

Lets the bundle control plane (count candidates, validate, and — crucially —
let ``bundle resume`` recognise valid finalized shards) work with the "sharded"
candidate transport, without depending on Reader_trunk/Executor_trunk. The shard
file format is byte-for-byte the one ``com.company.sink.ShardSink`` writes and
``Executor_trunk/shard_reader.py`` reads; see those for the full layout.

A shard is *finalized* only when it carries the ``FWSHEND1`` trailer; a partial
``.tmp`` or a truncated/corrupt shard fails :func:`validate` and is skipped — so
resume reuses only intact shards and reruns the Reader otherwise.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

FILE_MAGIC = b"FWSHARD1"
FILE_TRAILER = b"FWSHEND1"
REC_MAGIC = 0x52454300  # "REC\0"
END_MAGIC = 0x46494E00  # "FIN\0"
SHARD_EXT = ".fwshard"
TMP_EXT = ".tmp"
SHARD_GLOB = "*.fwshard"

_MASK64 = 0xFFFFFFFFFFFFFFFF


class ShardError(Exception):
    """A shard is not a valid finalized shard (partial, truncated, or corrupt)."""


def _read_exact(f, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise ShardError("unexpected EOF in shard")
    return b


def _fnv1a64(s: str) -> int:
    h = 0xcbf29ce484222325
    for x in s.encode("utf-8"):
        h ^= x
        h = (h * 0x100000001b3) & _MASK64
    return h


def is_finalized(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size < len(FILE_MAGIC) + len(FILE_TRAILER):
            return False
        with open(path, "rb") as f:
            head = f.read(len(FILE_MAGIC))
            f.seek(size - len(FILE_TRAILER))
            tail = f.read(len(FILE_TRAILER))
        return head == FILE_MAGIC and tail == FILE_TRAILER
    except OSError:
        return False


def iter_shard(path: Path):
    """Yield ``(candidate_id, content_bytes)`` for one finalized shard, CRC-checked.
    Raises :class:`ShardError` on a partial/corrupt shard or any CRC/trailer mismatch."""
    with open(path, "rb") as f:
        if _read_exact(f, len(FILE_MAGIC)) != FILE_MAGIC:
            raise ShardError(f"not a shard file (bad magic): {path}")
        count = 0
        xor = 0
        while True:
            marker_b = f.read(4)
            if len(marker_b) != 4:
                raise ShardError(f"shard not finalized (no trailer): {path}")
            (marker,) = struct.unpack(">i", marker_b)
            if marker == END_MAGIC:
                (rec_count,) = struct.unpack(">i", _read_exact(f, 4))
                (shard_xor,) = struct.unpack(">Q", _read_exact(f, 8))
                if _read_exact(f, len(FILE_TRAILER)) != FILE_TRAILER:
                    raise ShardError(f"bad shard trailer magic: {path}")
                if rec_count != count or shard_xor != xor:
                    raise ShardError(f"shard trailer reconciliation failed: {path}")
                return
            if marker != REC_MAGIC:
                raise ShardError(f"corrupt shard (bad record marker {marker:#x}) in {path}")
            (id_len,) = struct.unpack(">i", _read_exact(f, 4))
            if id_len < 0 or id_len > (1 << 20):
                raise ShardError(f"implausible id length {id_len} in {path}")
            cid = _read_exact(f, id_len).decode("utf-8")
            (raw_len,) = struct.unpack(">q", _read_exact(f, 8))
            (crc_expected,) = struct.unpack(">q", _read_exact(f, 8))
            (comp_len,) = struct.unpack(">i", _read_exact(f, 4))
            if raw_len < 0 or comp_len < 0:
                raise ShardError(f"implausible record lengths in {path}")
            comp = _read_exact(f, comp_len)
            try:
                raw = zlib.decompress(comp)
            except zlib.error as exc:
                raise ShardError(f"corrupt deflate stream for {cid} in {path}: {exc}")
            if len(raw) != raw_len:
                raise ShardError(f"inflated length {len(raw)} != {raw_len} for {cid} in {path}")
            if (zlib.crc32(raw) & 0xFFFFFFFF) != (crc_expected & 0xFFFFFFFF):
                raise ShardError(f"record CRC mismatch for {cid} in {path}")
            yield cid, raw
            count += 1
            xor = (xor ^ _fnv1a64(cid)) & _MASK64


def validate(path: Path) -> int:
    """Record count for a valid finalized shard, or ``-1`` if partial/corrupt."""
    try:
        n = 0
        for _ in iter_shard(path):
            n += 1
        return n
    except (ShardError, OSError, zlib.error):
        return -1


def list_finalized_shards(d: Path) -> list:
    """Finalized ``*.fwshard`` files in ``d``, deterministic name order, skipping ``.tmp``."""
    d = Path(d)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.name.endswith(SHARD_EXT) and not p.name.endswith(TMP_EXT))


def has_shards(d: Path) -> bool:
    """True iff directory ``d`` holds at least one ``*.fwshard`` file (sharded transport)."""
    return bool(list_finalized_shards(d))


def count_candidates(d: Path) -> int:
    """Total candidate records across all VALID finalized shards in ``d`` (corrupt → skipped)."""
    return sum(n for n in (validate(s) for s in list_finalized_shards(d)) if n >= 0)


def all_shards_valid(d: Path) -> bool:
    """True iff every ``*.fwshard`` in ``d`` validates (no truncated/corrupt shard)."""
    shards = list_finalized_shards(d)
    return bool(shards) and all(validate(s) >= 0 for s in shards)


def sources_dir_digest(names) -> str:
    """sha256 over a sorted name list, one ``name + "\\n"`` at a time — matches Reader's
    sha256OfLines / py_executor._sources_dir_digest, here over the shard-file names."""
    md = hashlib.sha256()
    for name in names:
        md.update((name + "\n").encode("utf-8"))
    return md.hexdigest()
