"""Local controls and consciously enabled external model adapters."""

from .base import (
    Adapter,
    AdapterInfrastructureError,
    Completion,
    CompletionRequest,
)
from .external import ExternalHTTPAdapter, ExternalHTTPConfig
from .local import FragileControlAdapter, OracleControlAdapter
from .registry import load_adapter

__all__ = (
    "Adapter",
    "AdapterInfrastructureError",
    "Completion",
    "CompletionRequest",
    "ExternalHTTPAdapter",
    "ExternalHTTPConfig",
    "FragileControlAdapter",
    "OracleControlAdapter",
    "load_adapter",
)
