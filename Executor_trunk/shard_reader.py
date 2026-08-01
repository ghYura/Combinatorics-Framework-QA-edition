"""STEP 32 — streaming reader for ShardSink compressed-shard containers.

This is the Executor-side counterpart of Reader_trunk's
``com.company.sink.ShardReader`` / ``ShardSink``: it lets the Python Executor
consume a ``candidate_transport == "sharded"`` Handoff v2 manifest. The shard
file format is byte-for-byte the one ShardSink writes::

    [8]  FILE_MAGIC  "FWSHARD1"
    repeated record (ascending candidate-id order):
      [4]  REC_MAGIC  "REC\\0"
      [4]  idLen        (int32, big-endian)
      [..] id           (idLen UTF-8 bytes)
      [8]  rawLen       (int64)  uncompressed content length (payload + tail)
      [8]  crc32        (int64)  CRC-32 of the uncompressed content
      [4]  compLen      (int32)
      [..] comp         (DEFLATE/zlib of the content)
    trailer (present only after a clean finalize):
      [4]  END_MAGIC  "FIN\\0"
      [4]  recordCount  (int32)
      [8]  shardIndexXor(int64)  XOR-fold of fnv1a64(id)
      [8]  FILE_TRAILER "FWSHEND1"

Each record is inflated one at a time (the whole shard is never expanded to
disk — STEP 32 action 4) and CRC-checked; a partial ``.tmp`` / truncated /
corrupt shard fails :func:`validate` and is skipped by :func:`iter_corpus`
(resume rebuilds it). Java's ``Deflater(level, nowrap=false)`` emits a zlib
stream, which ``zlib.decompress`` reads directly, and ``zlib.crc32`` is the
same CRC-32 as Java's ``java.util.zip.CRC32``.
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

_MASK64 = 0xFFFFFFFFFFFFFFFF


class ShardError(Exception):
    """A shard is not a valid finalized shard (partial, truncated, or corrupt)."""


def _read_exact(f, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise ShardError("unexpected EOF in shard")
    return b


def _fnv1a64(s: str) -> int:
    """64-bit FNV-1a — identical to ShardSink.fnv1a64 (unsigned 64-bit)."""
    h = 0xcbf29ce484222325
    for x in s.encode("utf-8"):
        h ^= x
        h = (h * 0x100000001b3) & _MASK64
    return h


def is_finalized(path: Path) -> bool:
    """Cheap O(1) probe: a finalized shard starts with FILE_MAGIC and ends with
    FILE_TRAILER. :func:`iter_shard`/:func:`validate` still do the full check."""
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
    """Yield ``(candidate_id, content_bytes)`` for one finalized shard, one record
    at a time. Raises :class:`ShardError` on a partial/corrupt shard or any CRC /
    trailer mismatch. Fully consuming the generator validates the trailer."""
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
                if rec_count != count:
                    raise ShardError(f"shard record-count mismatch (header={rec_count} "
                                     f"streamed={count}) in {path}")
                if shard_xor != xor:
                    raise ShardError(f"shard index/xor mismatch in {path}")
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
                raise ShardError(f"inflated length {len(raw)} != expected {raw_len} "
                                 f"for {cid} in {path}")
            if (zlib.crc32(raw) & 0xFFFFFFFF) != (crc_expected & 0xFFFFFFFF):
                raise ShardError(f"record CRC mismatch for {cid} in {path}")
            yield cid, raw
            count += 1
            xor = (xor ^ _fnv1a64(cid)) & _MASK64


def validate(path: Path) -> int:
    """Full end-to-end validation. Returns the record count for a valid finalized
    shard, or ``-1`` if the shard is partial/corrupt (so resume rebuilds it)."""
    try:
        n = 0
        for _ in iter_shard(path):
            n += 1
        return n
    except (ShardError, OSError, zlib.error):
        return -1


def list_finalized_shards(d: Path) -> list:
    """Finalized ``*.fwshard`` files in ``d``, deterministic name order, skipping ``.tmp``."""
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.name.endswith(SHARD_EXT) and not p.name.endswith(TMP_EXT))


def corpus_count(d: Path) -> int:
    """Total candidate records across all VALID finalized shards in ``d``."""
    total = 0
    for shard in list_finalized_shards(d):
        n = validate(shard)
        if n >= 0:
            total += n
    return total


def iter_corpus(d: Path):
    """Stream ``(candidate_id, content_bytes)`` across every finalized shard in ``d``
    (deterministic shard order), skipping any partial/corrupt shard."""
    for shard in list_finalized_shards(d):
        if not is_finalized(shard):
            continue
        yield from iter_shard(shard)


def sources_dir_digest(names) -> str:
    """sha256 over a sorted name list, one ``name + "\\n"`` at a time — identical to
    py_executor._sources_dir_digest and Reader's sha256OfLines, here over shard names."""
    md = hashlib.sha256()
    for name in names:
        md.update((name + "\n").encode("utf-8"))
    return md.hexdigest()
