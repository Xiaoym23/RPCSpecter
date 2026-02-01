# 通用 OSC 变异器
# core/osc_mutator.py
import json
from pathlib import Path
from typing import Dict, Any, Optional

class OSCMutator:
    """通用 OSC 变异器：任意 OSC 参数路径 + 动态函数优先」"""
    def __init__(self, method: str=""):
        self.method = method
        self.history = []

    # ---------- 通用 OSC 变异 ----------
    def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 1. 读当前方法的 OSC 清单
        osc_map = self._load_osc_map()
        if not osc_map:
            print("无 OSC → 直接返回")
            return payload   # 无 OSC → 直接返回
        else:
            print(f"OSC 清单为{osc_map}")

        # 2. 读动态工具函数清单
        tools = self._load_tools()
        # 这个 func_map 的构造可能有点问题
        # func_map = {t["path"]: t["func_name"] for t in tools if t["constraint"] == "OSC"}
        # func_map = {t["param"]: t["script"].split("def ")[1].split("(")[0] for t in tools if (t["constraint"] == "OSC" or t["constraint"] == "SPC")}
        func_map = {t["param"]: t["script"].split("def ")[1].split("(")[0] for t in tools if t["constraint"] == "OSC"}
        print("动态工具字典为 ", func_map)

        # 3. 逐路径变异
        for path, spec in osc_map.items():
            print("当前元素为", path)
            old = _deep_get(payload, path)
            # 获取函数名
            func_name = func_map.get(path)
            if func_name:
                # 3.1 优先调用动态生成函数
                mod = self._load_method_module()
                new = getattr(mod, func_name)()
                print("调用工具变异成功，变异值为 ", new)

            else:
                # 3.2 回退：读「去重全集」第一条作为值？
                # 这里变异出来的值是什么？
                # new = self._first_value(spec)
                # print("调用工具变异失败，取默认值为 ", new)

                # TODO 如果变异失败，则保留原来的值
                new = old

            _assign_payload(payload, path, new)
            self.history.append({"path": path, "old": old, "new": new})
        return payload

    # ---------- 辅助 ----------
    def _load_osc_map(self) -> Dict[str, dict]:
        file = Path(f"osc_spc/by_method.json")
        if not file.exists():
            return {}
        methods = json.loads(file.read_text())
        for m in methods:
            if m["method"] == self.method:
                return m["osc_spc"]
        return {}

    def _load_tools(self) -> list:
        # 工具函数加载
        file = Path(f"tools/generated/{self.method}.json")
        if not file.exists():
            return []
        return json.loads(file.read_text()).get("tools", [])

    def _load_method_module(self):
        import importlib.util
        py_file = Path(f"tools/generated/{self.method}.py")
        if not py_file.exists():
            return None
        spec = importlib.util.spec_from_file_location(self.method, py_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _first_value(self, spec: dict) -> Any:
        """从去重全集拿第一条值作为回退"""
        pool_file = Path(f"osc_spc/by_constraint.json")
        if not pool_file.exists():
            return None
        pool = json.loads(pool_file.read_text())
        for item in pool.get(spec["constraint"], []):
            # print(f'元素为 {item}')
            # print(f'规范为 {spec}')
            if item["path"] == spec["name"]:
                # 按类型返回空壳
                return _empty_value(item["type"])
        return None

# 同文件底部追加
def _deep_get(obj: dict, path: str) -> Any:
    for key in path.split("."):
        if "[" in key and "]" in key:
            key, idx = key.split("[", 1)
            idx = int(idx[:-1])
            obj = obj[key][idx]
        else:
            obj = obj[key]
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


# def _empty_value(typ: str) -> Any:
#     if "[]" in typ:        # 数组
#         return []
#     if "dict" in typ:      # 对象
#         return {}
#     if "int" in typ:       # 整数
#         return 0
#     if "str" in typ:       # 字符串
#         return ""
#     return None

# ------------------------------------------------------------------------------------------
# 只负责 minContextSlot 字段的链上状态约束变异
# # osc_mutator.py
# from tools.slot_tool import mutate_min_context_slot
# from typing import Any, Dict

# class MinContextSlotOSC:
#     """只负责 minContextSlot 字段的链上状态约束变异"""
#     def __init__(self):
#         self.history = []  # 用于后续合并器做权重调整

#     def mutate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
#         """原地改写 payload['object']['minContextSlot']"""
#         obj = payload.setdefault("object", {})
#         old = obj.get("minContextSlot")
#         new, reason = mutate_min_context_slot()
#         obj["minContextSlot"] = new
#         self.history.append({"old": old, "new": new, "reason": reason})
#         return payload