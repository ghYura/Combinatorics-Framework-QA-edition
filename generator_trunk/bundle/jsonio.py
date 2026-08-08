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

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from .models import to_dict

# Any mapping key containing one of these (case-insensitive) substrings is
# treated as carrying a secret and is replaced wholesale before it is ever
# written to a manifest, log, or report.
_SECRET_KEY_FRAGMENTS = ("password", "token", "secret", "api_key", "credential")
REDACTED = "***REDACTED***"


def write_json_atomic(path: "Path | str", data: Any) -> None:
    """Write *data* as JSON to *path* without ever exposing a partial file.

    Writes to a sibling temp file, flushes + fsyncs, then atomically replaces
    the target via ``os.replace`` (same filesystem ⇒ atomic on POSIX). Output is
    UTF-8, deterministically key-ordered, and ends with a single trailing
    newline.

    Secret-shaped fields (password/token/secret/api_key/credential, see
    :func:`redact`) are stripped *after* converting dataclasses to plain dicts —
    redacting the dataclass instance itself would be a no-op, since frozen
    dataclasses aren't mappings — so nothing reaches disk unredacted.
    """
    path = Path(path)
    text = json.dumps(redact(to_dict(data)), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_json(path: "Path | str") -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_secret_key(key: Any) -> bool:
    k = str(key).lower()
    return any(fragment in k for fragment in _SECRET_KEY_FRAGMENTS)


def redact(value: Any) -> Any:
    """Recursively replace mapping values whose key looks like a secret.

    Keys are matched case-insensitively against: password, token, secret,
    api_key, credential. Used before anything (manifest, resolved config,
    logs) reaches disk or stdout.
    """
    if isinstance(value, Mapping):
        return {k: (REDACTED if _is_secret_key(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value
