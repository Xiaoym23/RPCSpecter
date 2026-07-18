# core/osc_mutator.py
import json, os, random, hashlib, base64
from pathlib import Path
from typing import Dict, Any, Optional

# 按需继续扩展
import requests
import builtins

import re

def _extract_func_name(code: str) -> Optional[str]:
    """
    从字符串中提取第一个函数名
    例如: "def legal_minContextSlot():\n    ..." → "legal_minContextSlot"
    """
    match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code)
    if match:
        return match.group(1)
    return None

# SAFE_BUILTINS = {k: getattr(builtins, k) for k in
#                  {"len", "int", "str", "bool", "list", "dict", "any", "all", "range"}}

import builtins

SAFE_BUILTINS = {
    "__import__": builtins.__import__,
    "len": builtins.len,
    "int": builtins.int,
    "str": builtins.str,
    "bool": builtins.bool,
    "list": builtins.list,
    "dict": builtins.dict,
    "any": builtins.any,
    "all": builtins.all,
    "range": builtins.range,
    "isinstance": builtins.isinstance,
    "type": builtins.type,
    "hasattr": builtins.hasattr,
    "getattr": builtins.getattr,
    "setattr": builtins.setattr,
}

class OSCMutator:
    """OSC mutator: instantiate and perturb on-chain-state dependent parameters."""
    def __init__(self, method: str, chain: str = "ethereum"):
        self.method = method
        self.chain = chain
        self.history = []

    def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tools = self._load_tools()
        for tool in tools:
            if tool.get("constraint") != "OSC":
                continue
            path = tool.get("path") or tool.get("param", "")
            print("参数为", path)

            # print("OSC分隔后参数为", path.split(".")[-1])
            print("OSC原始负载为",payload)
            match = 0
            for p,v in payload.items():
                # key = _deep_get(p, path)
                print("OSC负载为", p)
                print("负载类型为", type(p))
                if isinstance(v, dict):
                    print(f'{p} 是字典')
                    for q in v:
                        print(f'q的值为{q}')
                        if q == path.split(".")[-1]:
                            print(f'要变异的OSC参数是 {path}')
                            match = 1
                            break
                else:                
                    if p == path.split(".")[-1]:
                        print(f'要变异的OSC参数是 {path}')
                        match = 1
                        break
            if match == 0:
                continue


            # 1. 动态注入合法值
            # func_code = tool["legal"]
            # print("代码为", func_code)

        #     new_val = self._exec_func(func_code, path)
        #     print("执行结果为", new_val)
        #     # 2. 回退：第一条值（无动态模块时）
        #     if new_val is None:
        #         new_val = self._first_value(path)
        #     old = _deep_get(payload, path)
        #     _assign_payload(payload, path, new_val)
        #     self.history.append({"path": path, "old": old, "new": new_val})
        # return payload
        # 1. 执行 legal 函数
            new_val = self._exec_func(tool.get("legal", ""), path)
            print("执行结果为", new_val)
            # 2. 无函数 → 回退第一条值
            if new_val is None:
                new_val = self._first_value(path)
            old = _deep_get(payload, path)
            _assign_payload(payload, path, new_val)
            self.history.append({"path": path, "old": old, "new": new_val})
        return payload

    # ---------- 辅助 ----------
    def _load_tools(self) -> list:
        candidates = [
            Path(f"ConstraintExtraction/tools/{self.chain}/tools.json"),
            Path(f"tools/{self.chain}/tools.json"),
            Path(f"tools/ethereum/tools.json"),
        ]
        for file in candidates:
            if file.exists():
                return json.loads(file.read_text()).get("tools", [])
        return []

    # def _exec_func(self, code: str, path: str) -> Any:
    #     """执行工具文件里的 legal 函数"""
    #     try:
    #         loc = {}
    #         exec(code, {"__builtins__": __builtins__}, loc)
    #         # 函数名 = path 的叶子名
    #         func_name = path.split(".")[-1]
    #         if func_name in loc:
    #             return loc[func_name]()
    #         # 无函数 → 回退
    #         return None
    #     except Exception:
    #         return None

    # ---------- 执行工具文件里的 legal 函数 ----------
    def _exec_func(self, code: str, path: str) -> Any:
        loc = {}
        clean_globals = {
            "__builtins__": SAFE_BUILTINS,
            "requests": requests,
            "os": os,
            "json": json,
            "base64": base64,
            "hashlib": hashlib,
            "random": random,
            # 按需继续加 solders.* 等
        }
        try:
            exec(code, clean_globals, loc)
            # print("loc为", loc["to"]())
            # func_name = path.split(".")[-1]
            func_name = _extract_func_name(code)
            print('函数名为', func_name)
            if func_name and func_name in loc:
                return loc[func_name]()
            # 函数不存在 → 回退
            return None
        except Exception as e:
            # ★ 必须打印，否则永远静默 None
            print(f"[ExecErr] {e} in {path}")
            return None

    def _first_value(self, path: str) -> Any:
        """读去重全集第一条值作为回退"""
        pool = self._load_pool()
        for item in pool.get("OSC", []):
            if item["path"] == path:
                return _empty_value(item["type"])
        return None

    def _load_pool(self) -> dict:
        candidates = [
            Path(f"osc_spc/{self.chain}/by_constraint.json"),
            Path("osc_spc/ethereum/by_constraint.json"),
        ]
        for file in candidates:
            if file.exists():
                return json.loads(file.read_text())
        return {}
    

# def _deep_get(obj: dict, path: str) -> Any:
#     for key in path.split("."):
#         if "[" in key and "]" in key:
#             key, idx = key.split("[", 1)
#             idx = int(idx[:-1])
#             obj = obj[key][idx]
#         else:
#             obj = obj[key]
#     return obj

# 不知道哪个深度获取的函数是正确的？
# def _deep_get(obj: Dict[str, Any], path: str) -> Any:
#     print('obj的值为', obj)
#     obj = obj.get('params')
#     for key in path.split("."):
#         print('分割后为', key)
#         if "[" in key and "]" in key:        # list[0]
#             key, idx = key.split("[", 1)
#             idx = int(idx[:-1])
#             obj = obj.get(key, [{}])         # 缺失返回空列表
#             if len(obj) <= idx:
#                 return None
#             obj = obj[idx]
#         else:
#             if obj is None:
#                 return None
#             else:
#                 obj = obj.get(key)               # 缺失返回 None
#         if obj is None:
#             return None
#     return obj

def _deep_get(obj: dict, path: str) -> Any:
    for key in path.split("."):
        if "[" in key and "]" in key:
            key, idx = key.split("[", 1)
            idx = int(idx[:-1])
            obj = obj[key][idx] if key in obj and isinstance(obj[key], list) else None
        else:
            obj = obj.get(key) if isinstance(obj, dict) else None
        if obj is None:
            return None
    return obj

def _assign_payload(payload: dict, path: str, value: Any) -> None:
    print(f"osc 变异器输入为 \n{payload} \n{path} \n{value}")
    if "." not in path:
        payload[path] = value
        return
    keys = path.split(".")
    last = keys.pop()
    cur = payload
    for k in keys:
        cur = cur.setdefault(k, {})
    # 加这一行可以避免给
    if last in cur:
        cur[last] = value

def _empty_value(typ: str) -> Any:
    """仅决定空壳形状"""
    if "array" in typ or "[]" in typ or "array<number>" in typ or "array[string]" in typ:
        return []
    if typ in ("object", "dict"):
        return {}
    if typ in ("int", "integer", "u64", "number"):
        return 0
    if typ in ("string", ""):
        return ""
    if typ == "boolean":
        return False
    return None