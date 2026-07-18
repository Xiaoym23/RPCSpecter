"""STC primitive/boundary mutator.

This module keeps the legacy class name BasicTypeBTC for compatibility, but it is
used as part of the RPCSpecter STC mutator family.  If an optional project-local
`tools.btc_tool.mutate_basic` exists, it is used; otherwise a small built-in pool
is used so the repository remains importable out of the box.
"""
from __future__ import annotations

import random
from typing import Any, Dict, Optional

try:
    from tools.btc_tool import mutate_basic as _external_mutate_basic
except Exception:  # pragma: no cover - optional generated helper
    _external_mutate_basic = None


_FALLBACK_POOLS = {
    "maxRetries": [(0, "lower-bound"), (1, "small-valid"), (2**31 - 1, "large-valid"), (-1, "negative-invalid"), ("1", "wrong-type")],
    "skipPreflight": [(False, "valid-bool"), (True, "valid-bool"), ("false", "wrong-type"), (None, "null")],
    "minContextSlot": [(0, "lower-bound"), (1, "small-valid"), (-1, "negative-invalid"), (2**64, "u64-overflow")],
}


def _fallback_mutate_basic(field: str) -> tuple[Any, str]:
    pool = _FALLBACK_POOLS.get(field, [(None, "null-fallback")])
    return random.choice(pool)


class BasicTypeBTC:
    def __init__(self, chain: Optional[str] = None):
        self.chain = chain
        self.history = []

    def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Prototype-compatible STC boundary mutation for common Solana config fields.
        obj = payload.setdefault("object", {})
        mutate_basic = _external_mutate_basic or _fallback_mutate_basic
        for field in ("maxRetries", "skipPreflight", "minContextSlot"):
            if field not in obj:
                continue
            new, reason = mutate_basic(field)
            obj[field] = new
            self.history.append({"constraint": "STC", "field": field, "new": new, "reason": reason})
        return payload
