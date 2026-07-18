# core/spc_mutator.py
import json, os, random, hashlib, base64
from pathlib import Path
from typing import Dict, Any, List
import requests
import builtins
import re
import importlib  # ← 新增：用于动态导入模块

SAFE_BUILTINS = {
    "__import__": builtins.__import__,
    "len": builtins.len,
    "bytes": builtins.bytes,
    "tuple": builtins.tuple,
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


class TransactionSPC:
    """PDC mutator: legacy SPC-compatible implementation for procedural constraints."""
    def __init__(self, chain: str = "ethereum"):
        self.chain = chain
        self.history = []

    def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tools = self._load_tools()
        for tool in tools:
            if tool.get("constraint") not in {"PDC", "SPC"}:
                continue
            path = tool.get("path") or tool.get("param", "")
            
            print("分隔后参数为", path.split(".")[-1])
            match = 0
            for p in payload:
                # key = _deep_get(payload, p)
                # print("负载为", key)
                if p == path:
                    print(f'要变异的SPC参数是 {path}')
                    match = 1
                    break
            if match == 0:
                continue

            # 如果 payload 中不存在该参数路径，则跳过（避免不必要的变异）
            if not self._path_exists(payload, path):
                continue

            chain_variants = tool.get("chain_variants", {})

            if not chain_variants:
                # 单步 SPC → 直接合法值（传入 imports）
                new_val = self._exec_single(tool.get("legal", ""), path, tool.get("imports", []))
            else:
                # 链式 A→B→C→D（传入 imports）
                new_val = self._chain_process(chain_variants, path, tool.get("imports", []))

            # 回退逻辑
            if new_val is None:
                new_val = self._first_value(path)

            _assign_payload(payload, path, new_val)
            self.history.append({
                "path": path,
                "chain": list(chain_variants.keys()) if chain_variants else [],
                "new": new_val
            })
        return payload

    # ---------- 检查 path 是否存在 ----------
    def _path_exists(self, payload: Dict[str, Any], path: str) -> bool:
        """检查 payload 中是否存在该路径"""
        try:
            _deep_get(payload, path)
            return True
        except (KeyError, TypeError, AttributeError):
            return False

    # ---------- 链式过程：每一步都 exec 执行 ----------
    def _chain_process(self, variants: dict, path: str, imports: List[str]) -> Any:
        """A→B→C→D，每一步都 exec 执行 legal/illegal"""
        intermediate = None
        for step_name, step_variants in variants.items():
            # 50% 合法，50% 非法
            variant_type = "legal" if (os.urandom(1)[0] & 1) else "illegal"
            code = step_variants[variant_type]  # 取出代码字符串

            # 执行这一步（传入 imports）
            step_result = self._exec_step(code, step_name, intermediate, imports)
            print(f'{step_name} 步骤的执行结果为 {step_result}')
            if step_result is None:
                # 任何一步失败 → 整个链回退
                return self._first_value(path)
            intermediate = step_result

        return intermediate

    # ---------- 执行单步（带参数传递和动态 imports）----------
    def _exec_step(self, code: str, step_name: str, intermediate: Any, imports: List[str]) -> Any:
        """执行链中的一步，支持传入 intermediate 和动态导入 modules"""
        loc = {}
        # 基础 clean_globals
        clean_globals = {
            "__builtins__": SAFE_BUILTINS,
            "requests": requests,
            "os": os,
            "json": json,
            "base64": base64,
            "hashlib": hashlib,
            "random": random,
        }
        print('要导入的库为', imports)
        # ★ 动态加载 imports 列表中的模块（解决 No module named 'eth_utils'）
        for imp in imports:
            try:
                if "." in imp:  # 子模块，如 eth_hash.auto
                    module = importlib.import_module(imp)
                else:
                    module = __import__(imp)
                # 只取顶层名放入 globals，如 eth_utils
                top_name = imp.split(".")[0]
                clean_globals[top_name] = module
            except Exception as e:
                print(f"[ImportWarn] {e} for {imp} in {step_name}")

        try:
            exec(code, clean_globals, loc)
            func_name = self._extract_func_name(code)
            if func_name and func_name in loc:
                # 如果函数需要参数，传 intermediate
                if intermediate is not None:
                    return loc[func_name](intermediate)
                else:
                    return loc[func_name]()
            return None
        except Exception as e:
            print(f"[ChainExecErr] {e} in {step_name}")
            return None

    # ---------- 单步 SPC ----------
    def _exec_single(self, code: str, path: str, imports: List[str]) -> Any:
        """执行单步 SPC 函数（支持动态 imports）"""
        loc = {}
        clean_globals = {
            "__builtins__": SAFE_BUILTINS,
            "requests": requests,
            "os": os,
            "json": json,
            "base64": base64,
            "hashlib": hashlib,
            "random": random,
        }
        # ★ 动态加载 imports
        for imp in imports:
            try:
                if "." in imp:
                    module = importlib.import_module(imp)
                else:
                    module = __import__(imp)
                top_name = imp.split(".")[0]
                clean_globals[top_name] = module
            except Exception as e:
                print(f"[ImportWarn] {e} for {imp} in {path}")

        try:
            exec(code, clean_globals, loc)
            func_name = self._extract_func_name(code)
            if func_name and func_name in loc:
                return loc[func_name]()
            return None
        except Exception as e:
            print(f"[ExecErr] {e} in {path}")
            return None

    # ---------- 提取函数名 ----------
    def _extract_func_name(self, code: str) -> str:
        match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code)
        if match:
            return match.group(1)
        return None

    # ---------- 辅助 ----------
    def _load_tools(self) -> list:
        candidates = [
            Path(f"ConstraintExtraction/tools/{self.chain}/tools.json"),
            Path(f"tools/{self.chain}/tools.json"),
            Path("tools/ethereum/tools.json"),
        ]
        for file in candidates:
            if file.exists():
                return json.loads(file.read_text()).get("tools", [])
        return []

    def _first_value(self, path: str) -> Any:
        """读去重全集第一条值作为回退"""
        pool = self._load_pool()
        for item in pool.get("PDC", []) + pool.get("SPC", []):
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


# ---------- 通用工具 ----------
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
    if "." not in path:
        payload[path] = value
        return
    keys = path.split(".")
    last = keys.pop()
    cur = payload
    for k in keys:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[last] = value

def _empty_value(typ: str) -> Any:
    if typ in ("array", "array<string>", "array<number>") or "[]" in typ:
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