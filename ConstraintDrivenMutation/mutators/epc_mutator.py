#!/usr/bin/env python3
"""通用 EPC 变异器：穷举所有 (合法+空+非法) 组合，每次取 1 条」"""
import json
from pathlib import Path
from typing import Dict, Any, List
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from .epc_combinator import generate_epc_combinations, _assign_payload, _deep_get
from copy import deepcopy

class EncodingEPC:
    """通用 EPC 变异器：不再硬编码字段，不再硬编码值」"""
    def __init__(self, method: str):
        self.method = method
        self.history = []
        # 1. 生成本方法所有 EPC 组合（合法+空+非法）
        self._combos = generate_epc_combinations(method)   # list[dict]
        self._index = 0                                    # 轮询索引

    # ---------- 通用 EPC 变异 ----------
    def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self._combos:
            return payload   # 无 EPC → 直接返回

        # 1. 轮询取 1 条组合（Cartesian 积）
        combo = self._combos[self._index]
        self._index = (self._index + 1) % len(self._combos)

        # 2. 逐子路径赋值（支持无限嵌套）
        for sub_path, value in combo.items():
            old = _deep_get(payload, sub_path)
            _assign_payload(payload, sub_path, value)
            self.history.append({"path": sub_path, "old": old, "new": value})

        return payload
    
# # epc_mutator.py
# from tools.epc_tool import sample_epc, EPC_POOL
# from typing import Any, Dict

# class EncodingEPC:
#     """负责所有 EPC 字段的集合内采样 + 联动回写"""
#     def __init__(self):
#         self.history = []

#     def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
#         obj = payload.setdefault("object", {})
#         # 1. 处理 encoding
#         enc, is_neg, reason = sample_epc("encoding")
#         if not is_neg:
#             obj["encoding"] = enc
#             # 联动：重新编码 transaction
#             # TODO: 不是每个方法都有交易参数需要变异
#             # sync_tx_encoding(payload, enc)
#         else:
#             obj["encoding"] = enc  # 故意越界

#         # 2. 处理 preflightCommitment
#         com, _, _ = sample_epc("preflightCommitment")
#         obj["preflightCommitment"] = com

#         self.history.append({"encoding": enc, "commitment": com, "reason": reason})
#         return payload

# # 内部工具
# def sync_tx_encoding(payload: dict, new_enc: str):
#     from tools.tx_tool import mutate_transaction
#     tx, _ = mutate_transaction(new_enc)
#     payload["transaction"] = tx