"""Syntax Constraint (STC) mutator.

STC covers syntax-only validity: primitive type/range boundaries, enumerated
value domains, payload-size limits, and cross-parameter compatibility.  It first
uses generated value pools, then falls back to built-in Ethereum/Solana pools.
"""
from __future__ import annotations

import itertools
import random
from typing import Any, Dict, List, Optional

from .common import assign_payload, constraint_kind, deep_get, exec_generated_func, load_tools, path_exists


SOLANA_POOLS = {
    "commitment": ["processed", "confirmed", "finalized", "", "unknown", "pending", None],
    "encoding": ["base58", "base64", "base64+zstd", "jsonParsed", "", "raw", "hex", None],
    "preflightCommitment": ["processed", "confirmed", "finalized", "", "unknown", "pending", None],
    "transactionDetails": ["full", "signatures", "none", "", "hash", "meta", None],
    "filter": ["circulating", "nonCirculating", "", "all", "none", None],
    "maxRetries": [0, 1, 2**31 - 1, -1, "1"],
    "skipPreflight": [False, True, "false", None],
    "minContextSlot": [0, 1, -1, 2**64],
}

ETHEREUM_POOLS = {
    "fromBlock": ["earliest", "latest", "pending", "safe", "finalized", "", "0x-1", "latest+1", None],
    "toBlock": ["earliest", "latest", "pending", "safe", "finalized", "", "0x-1", "latest+1", None],
    "blockNumber": ["earliest", "latest", "pending", "safe", "finalized", "", "0x-1", "latest+1", None],
    "blockReference": ["earliest", "latest", "pending", "safe", "finalized", "", "0x-1", "latest+1", None],
    "tracer": ["callTracer", "prestateTracer", "", "opcodeTracer", "raw", None],
    "subscription_name": ["newHeads", "logs", "newPendingTransactions", "", "blocks", "txs", None],
    "gas": ["0x5208", 21000, "", -1, None],
    "gasPrice": ["0x1", 1, "", -1, None],
    "value": ["0x0", 0, "", -1, None],
}


class STCMutator:
    def __init__(self, method: str, chain: str = "ethereum"):
        self.method = method
        self.chain = chain
        self.history: list[dict[str, Any]] = []
        self._tools = load_tools(chain, method)
        self._combos = self._build_combinations()
        self._index = 0

    def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._combos:
            combo = self._combos[self._index]
            self._index = (self._index + 1) % len(self._combos)
            for path, value in combo.items():
                if path_exists(payload, path):
                    old = deep_get(payload, path)
                    assign_payload(payload, path, value)
                    self.history.append({"constraint": "STC", "path": path, "old": old, "new": value, "source": "pool"})
            self._apply_dependency_rules(payload)
            return payload

        self._fallback_walk(payload)
        self._apply_dependency_rules(payload)
        return payload

    def _build_combinations(self) -> List[Dict[str, Any]]:
        pools: Dict[str, List[Any]] = {}
        for tool in self._tools:
            if constraint_kind(tool) != "STC":
                continue
            path = tool.get("path") or tool.get("param", "")
            if not path:
                continue
            values = self._values_from_tool(tool, path)
            if values:
                pools[path] = values
        if not pools:
            return []
        keys = list(pools.keys())
        # Avoid exploding memory on highly-parameterized methods.  Keep a stable,
        # rotating sample of combinations while preserving per-field coverage.
        total = 1
        for k in keys:
            total *= max(1, len(pools[k]))
        if total <= 2048:
            return [dict(zip(keys, vals)) for vals in itertools.product(*(pools[k] for k in keys))]
        combos: List[Dict[str, Any]] = []
        max_len = max(len(pools[k]) for k in keys)
        for i in range(max_len):
            combos.append({k: pools[k][i % len(pools[k])] for k in keys})
        for _ in range(min(256, total)):
            combos.append({k: random.choice(pools[k]) for k in keys})
        return combos

    def _values_from_tool(self, tool: Dict[str, Any], path: str) -> List[Any]:
        vals: List[Any] = []
        for key in ("value_pool", "boundary_pool"):
            pool = tool.get(key) or {}
            if isinstance(pool, dict):
                for name in ("legal", "valid", "empty", "illegal", "invalid"):
                    vals.extend(pool.get(name, []))
            elif isinstance(pool, list):
                vals.extend(pool)
        if vals:
            return vals
        leaf = path.split(".")[-1]
        return self._default_pool(leaf) or self._default_pool(path) or []

    def _apply_dependency_rules(self, payload: Dict[str, Any]) -> None:
        """Apply generated cross-parameter mutation rules when available.

        Supported lightweight artifact forms:
        - {"assign": {"path": value, ...}}
        - {"path": "object.encoding", "values": [..]}
        - {"path": "object.encoding", "value": "..."}
        - {"generator": "def make(): ..."}
        """
        for tool in self._tools:
            if constraint_kind(tool) != "STC":
                continue
            for rule in tool.get("dependency_rules", []) or []:
                if not isinstance(rule, dict):
                    continue
                assigns = rule.get("assign")
                if isinstance(assigns, dict):
                    for path, value in assigns.items():
                        if path_exists(payload, path):
                            old = deep_get(payload, path)
                            assign_payload(payload, path, value)
                            self.history.append({"constraint": "STC", "path": path, "old": old, "new": value, "source": "dependency"})
                    continue
                path = rule.get("path")
                if path and path_exists(payload, path):
                    if "values" in rule and isinstance(rule["values"], list) and rule["values"]:
                        value = random.choice(rule["values"])
                    elif "value" in rule:
                        value = rule["value"]
                    elif "generator" in rule:
                        value = exec_generated_func(rule.get("generator", ""), rule.get("imports", []))
                    else:
                        continue
                    old = deep_get(payload, path)
                    assign_payload(payload, path, value)
                    self.history.append({"constraint": "STC", "path": path, "old": old, "new": value, "source": "dependency"})

    def _default_pool(self, name: str) -> Optional[List[Any]]:
        return (ETHEREUM_POOLS if self.chain == "ethereum" else SOLANA_POOLS).get(name)

    def _fallback_walk(self, obj: Dict[str, Any], prefix: str = "") -> None:
        for key, value in list(obj.items()):
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._fallback_walk(value, path)
                continue
            pool = self._default_pool(key) or self._default_pool(path)
            if not pool:
                continue
            new = random.choice(pool)
            obj[key] = new
            self.history.append({"constraint": "STC", "path": path, "old": value, "new": new, "source": "fallback"})
