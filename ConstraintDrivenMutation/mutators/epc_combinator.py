#!/usr/bin/env python3
"""EPC 取值池 + 穷举组合生成器（读 by_method.json）"""
import json
import itertools
from pathlib import Path
from typing import Dict, List, Any

# ---------- 1. 取值池（三档） ----------
EPC_VALUE_POOL = {
    "commitment": {
        "legal": ["processed", "confirmed", "finalized"],
        "empty": [""],
        "illegal": ["unknown", "pending", None]
    },
    "encoding": {
        "legal": ["base58", "base64", "base64+zstd", "jsonParsed"],
        "empty": [""],
        "illegal": ["raw", "hex", None]
    },
    "filter": {
        "legal": ["circulating", "nonCirculating"],
        "empty": [""],
        "illegal": ["all", "none", None]
    },
    "transactionDetails": {
        "legal": ["full", "signatures", "none"],
        "empty": [""],
        "illegal": ["hash", "meta", None]
    },
    "preflightCommitment": {
        "legal": ["processed", "confirmed", "finalized"],
        "empty": [""],
        "illegal": ["unknown", "pending", None]
    }
}

ETH_EPC_VALUE_POOL = {
    # 块范围类
    "fromBlock": {
        "legal": ["earliest", "latest", "pending", "safe", "finalized"],
        "empty": [""],
        "illegal": ["0x-1", "latest+1", None]
    },
    "toBlock": {
        "legal": ["earliest", "latest", "pending", "safe", "finalized"],
        "empty": [""],
        "illegal": ["0x-1", "latest+1", None]
    },
    "blockNumber": {
        "legal": ["earliest", "latest", "pending", "safe", "finalized"],
        "empty": [""],
        "illegal": ["0x-1", "latest+1", None]
    },
    "newestBlock": {
        "legal": ["earliest", "latest", "pending", "safe", "finalized"],
        "empty": [""],
        "illegal": ["0x-1", "latest+1", None]
    },
    "SIMULATION_CONTEXT.blockNumber or Tag": {
        "legal": ["latest", "earliest", "pending", "safe", "finalized"],
        "empty": [""],
        "illegal": ["0x-1", "latest+1", None]
    },

    # 追踪/状态类
    "vmTrace": {
        "legal": ["full", "fast"],
        "empty": [""],
        "illegal": ["slow", "detail", None]
    },
    "trace": {
        "legal": ["callTracer", "prestateTracer"],
        "empty": [""],
        "illegal": ["opcodeTracer", "raw", None]
    },
    "stateDiff": {
        "legal": ["true"],
        "empty": [""],
        "illegal": ["false", "full", None]
    },

    # 订阅类
    "subscription_name": {
        "legal": ["newHeads", "logs", "newPendingTransactions"],
        "empty": [""],
        "illegal": ["blocks", "txs", None]
    },
    "subscription_name.newHeads": {
        "legal": ["newHeads"],
        "empty": [""],
        "illegal": ["newBlocks", None]
    },
    "subscription_name.logs": {
        "legal": ["logs"],
        "empty": [""],
        "illegal": ["events", None]
    },
    "subscription_name.newPendingTransactions": {
        "legal": ["newPendingTransactions"],
        "empty": [""],
        "illegal": ["pendingTxs", None]
    },

    # 其他枚举
    "blockReference": {
        "legal": ["earliest", "latest", "pending", "safe", "finalized"],
        "empty": [""],
        "illegal": ["0x-1", "latest+1", None]
    },
    "object.tracer": {
        "legal": ["callTracer", "prestateTracer"],
        "empty": [""],
        "illegal": ["opcodeTracer", "raw", None]
    }
}

def full_pool(param_name: str) -> List[Any]:
    # pool = EPC_VALUE_POOL.get(param_name, {})
    pool = ETH_EPC_VALUE_POOL.get(param_name, {})
    return pool.get("legal", []) + pool.get("empty", []) + pool.get("illegal", [])

# ---------- 2. 读指定方法的 EPC 段 ----------
def load_method_epc(method: str) -> Dict[str, dict]:
    file = Path("epc/ethereum/by_method.json")
    if not file.exists():
        return {}
    methods = json.loads(file.read_text())
    for m in methods:
        if m["method"] == method:
            return m.get("epc", {})   # 只返回 EPC 段
    return {}

# ---------- 3. 穷举组合生成器 ----------
def generate_epc_combinations(method: str) -> List[Dict[str, Any]]:
    epc_map = load_method_epc(method)
    if not epc_map:
        print(f"没找到{method}方法")
        return []
    print(f"epc 映射为：{epc_map}")
    # 1. 为每个 EPC 参数生成「合法 + 空 + 非法」值池
    pools: Dict[str, List[Any]] = {}
    for path, spec in epc_map.items():
        param_name = path.split(".")[-1]  # object.xxx → xxx
        pools[path] = full_pool(param_name)
    print('组合池为', pools)
    # 2. Cartesian 积：所有组合
    keys = list(pools.keys())
    values = list(pools.values())
    cartesian = itertools.product(*values)

    # 3. 转成 list[dict]（每条是一个完整 object 子树）
    combinations = []
    for combo in cartesian:
        combo_dict = {}
        for key, val in zip(keys, combo):
            _assign_payload(combo_dict, key, val)
        combinations.append(combo_dict)
    print("所有组合为", combinations)
    return combinations

# ---------- 4. 路径赋值工具 ----------
def _assign_payload(obj: dict, path: str, value: Any) -> None:
    if "." not in path:
        obj[path] = value
        return
    keys = path.split(".")
    last = keys.pop()
    cur = obj
    for k in keys:
        cur = cur.setdefault(k, {})
    cur[last] = value

# #!/usr/bin/env python3
# """EPC 取值池 + 笛卡尔积生成器（无限嵌套通用）"""
# import json
# import itertools
# from pathlib import Path
# from typing import Dict, List, Any, Tuple

# # ========== 1. 取值池（按叶子名索引） ==========
# EPC_VALUE_POOL = {
#     "commitment": {
#         "legal": ["processed", "confirmed", "finalized"],
#         "empty": [""],
#         "illegal": ["unknown", "pending", None]
#     },
#     "encoding": {
#         "legal": ["base58", "base64", "base64+zstd", "jsonParsed"],
#         "empty": [""],
#         "illegal": ["raw", "hex", None]
#     },
#     "filter": {
#         "legal": ["circulating", "nonCirculating"],
#         "empty": [""],
#         "illegal": ["all", "none", None]
#     },
#     "transactionDetails": {
#         "legal": ["full", "signatures", "none"],
#         "empty": [""],
#         "illegal": ["hash", "meta", None]
#     },
#     "preflightCommitment": {
#         "legal": ["processed", "confirmed", "finalized"],
#         "empty": [""],
#         "illegal": ["unknown", "pending", None]
#     }
# }

# def full_pool(param_name: str) -> List[Any]:
#     """返回「合法 + 空 + 非法」全集"""
#     pool = EPC_VALUE_POOL.get(param_name, {})
#     return pool.get("legal", []) + pool.get("empty", []) + pool.get("illegal", [])

# def leaf_name(path: str) -> str:
#     """object.dataSlice.offset → offset"""
#     return path.split(".")[-1]

# # ========== 2. 笛卡尔积生成器 ==========
# def generate_epc_combinations(method: str) -> List[Dict[str, Any]]:
#     """返回：所有 EPC 参数的 (合法+空+非法) 的 Cartesian 积"""
#     pool_file = Path(f"epc/by_method.json")
#     if not pool_file.exists():
#         # print("没找到epc的JSON文件")
#         return []

#     pool = json.loads(pool_file.read_text())
#     # 只取 object.* 的 EPC 参数
#     epc_params = [item for item in pool.get("EPC", []) if item.get("path", "").startswith("object.")]
#     # print("epc_params", epc_params)
#     # 1. 为每个 EPC 参数生成「合法+空+非法」值池
#     pools: Dict[str, List[Any]] = {}
#     for item in epc_params:
#         path = item["path"]
#         param_name = leaf_name(path)
#         pools[path] = full_pool(param_name)   # 全集

#     # 2. Cartesian 积：所有组合
#     keys = list(pools.keys())
#     values = list(pools.values())
#     cartesian = itertools.product(*values)

#     # 3. 转成 list[dict]（每条是一个完整 object 子树）
#     combinations = []
#     for combo in cartesian:
#         combo_dict = {}
#         for key, val in zip(keys, combo):
#             _assign_payload(combo_dict, key, val)
#         combinations.append(combo_dict)
#     print("所有组合为", combinations)
#     return combinations

# # ========== 3. 路径赋值工具 ==========
# def _assign_payload(obj: dict, path: str, value: Any) -> None:
#     """支持 object.x.y.z 点路径赋值"""
#     if "." not in path:
#         obj[path] = value
#         return
#     keys = path.split(".")
#     last = keys.pop()
#     cur = obj
#     for k in keys:
#         cur = cur.setdefault(k, {})
#     cur[last] = value

def _deep_get(obj: Dict[str, Any], path: str) -> Any:
    print('obj的值为', obj)
    obj = obj.get('params')
    for key in path.split("."):
        print('分割后为', key)
        if "[" in key and "]" in key:        # list[0]
            key, idx = key.split("[", 1)
            idx = int(idx[:-1])
            obj = obj.get(key, [{}])         # 缺失返回空列表
            if len(obj) <= idx:
                return None
            obj = obj[idx]
        else:
            if obj is None:
                return None
            else:
                obj = obj.get(key)               # 缺失返回 None
        if obj is None:
            return None
    return obj