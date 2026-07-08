"""BiocoreagentV2.0: research harness plus bioinformatics domain capabilities."""

from __future__ import annotations

import sys
from pathlib import Path


_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

_loaded_corecoder = sys.modules.get("corecoder")
_loaded_path = Path(getattr(_loaded_corecoder, "__file__", "")).resolve() if _loaded_corecoder else None
if _loaded_path and _PACKAGE_ROOT not in _loaded_path.parents:
    for _module_name in list(sys.modules):
        if _module_name == "corecoder" or _module_name.startswith("corecoder."):
            del sys.modules[_module_name]

from .runtime import BioPico
from .orchestrator import AsyncMultiAgentOrchestrator

__all__ = ["AsyncMultiAgentOrchestrator", "BioPico"]
