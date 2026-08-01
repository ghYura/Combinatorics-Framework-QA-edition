from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .registry import slug_tenant


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TokenAuth:
    """Bearer token -> tenant mapping loaded from an operator-owned JSON file."""

    def __init__(self, tokens_path: "Path | str"):
        self.tokens_path = Path(tokens_path)
        self._tokens = self._load(self.tokens_path)

    def _load(self, path: Path) -> dict[str, str]:
        if not path.exists():
            raise AuthError(
                "UNAUTHENTICATED",
                f"tokens file {path} does not exist; create a JSON token->tenant mapping and restart",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AuthError("UNAUTHENTICATED", f"tokens file {path} is not valid JSON: {exc}") from exc
        mapping = data.get("tokens") if isinstance(data, Mapping) and "tokens" in data else data
        if not isinstance(mapping, Mapping) or not mapping:
            raise AuthError("UNAUTHENTICATED", f"tokens file {path} must contain a non-empty token->tenant object")
        out = {}
        for token, tenant in mapping.items():
            token = str(token)
            if not token:
                raise AuthError("UNAUTHENTICATED", "tokens file contains an empty token")
            out[token] = slug_tenant(str(tenant))
        return out

    def authenticate(self, authorization: str | None) -> str:
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix):
            raise AuthError("UNAUTHENTICATED", "missing Authorization: Bearer <token>")
        token = authorization[len(prefix):].strip()
        tenant = self._tokens.get(token)
        if not tenant:
            raise AuthError("UNAUTHENTICATED", "unknown bearer token")
        return tenant
