"""On-chain State Constraint (OSC) mutator.

OSC parameters must be backed by live or historical chain state.  This mutator
uses generated legal helpers to instantiate real state and generated illegal /
boundary helpers to forge non-existing, expired, pruned, or out-of-range state.
"""
from __future__ import annotations

import random
from typing import Any, Dict

from .common import assign_payload, constraint_kind, deep_get, exec_generated_func, fallback_value, load_tools, path_exists


class OSCMutator:
    def __init__(self, method: str, chain: str = "ethereum", invalid_rate: float = 0.5, boundary_rate: float = 0.2):
        self.method = method
        self.chain = chain
        self.invalid_rate = invalid_rate
        self.boundary_rate = boundary_rate
        self.history: list[dict[str, Any]] = []

    def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        for tool in load_tools(self.chain, self.method):
            if constraint_kind(tool) != "OSC":
                continue
            path = tool.get("path") or tool.get("param", "")
            if not path or not path_exists(payload, path):
                continue

            mode = self._choose_mode(tool)
            new_val = exec_generated_func(tool.get(mode, ""), tool.get("imports", []))
            if new_val is None and mode != "legal":
                # Keep the request near-valid if the negative/boundary helper fails.
                mode = "legal"
                new_val = exec_generated_func(tool.get("legal", ""), tool.get("imports", []))
            if new_val is None:
                new_val = fallback_value(self.chain, "OSC", path)
            if new_val is None:
                continue

            old = deep_get(payload, path)
            assign_payload(payload, path, new_val)
            self.history.append({"constraint": "OSC", "path": path, "mode": mode, "old": old, "new": new_val})
        return payload

    def _choose_mode(self, tool: Dict[str, Any]) -> str:
        if tool.get("boundary") and random.random() < self.boundary_rate:
            return "boundary"
        if tool.get("illegal") and random.random() < self.invalid_rate:
            return "illegal"
        return "legal"
