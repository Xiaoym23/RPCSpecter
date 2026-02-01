# btc_mutator.py
from tools.btc_tool import mutate_basic

class BasicTypeBTC:
    def __init__(self):
        self.history = []

    def mutate(self, payload: dict) -> dict:
        obj = payload.setdefault("object", {})
        for f in ("maxRetries", "skipPreflight", "minContextSlot"):
            new, reason = mutate_basic(f)
            obj[f] = new
            self.history.append({"field": f, "new": new, "reason": reason})
        return payload