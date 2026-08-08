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

"""Local controls and consciously enabled external model adapters."""

from .base import (
    Adapter,
    AdapterInfrastructureError,
    Completion,
    CompletionRequest,
)
from .external import ExternalHTTPAdapter, ExternalHTTPConfig
from .local import (
    FragileControlAdapter,
    InjectableControlAdapter,
    OracleControlAdapter,
)
from .registry import load_adapter

__all__ = (
    "Adapter",
    "AdapterInfrastructureError",
    "Completion",
    "CompletionRequest",
    "ExternalHTTPAdapter",
    "ExternalHTTPConfig",
    "FragileControlAdapter",
    "InjectableControlAdapter",
    "OracleControlAdapter",
    "load_adapter",
)
