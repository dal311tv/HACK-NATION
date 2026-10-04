"""Least-privilege policy: deny tools inherited from personal Claude account connectors."""
from __future__ import annotations

DEFAULT_BLOCKED_PREFIXES = ("mcp__claude_ai_",)


def make_least_privilege_policy(blocked_prefixes: list[str] | None = None):
    prefixes = tuple(blocked_prefixes or DEFAULT_BLOCKED_PREFIXES)

    def evaluate(event):
        if event.get("type") != "tool_call":
            return None
        data = event.get("data") or {}
        name = str(data.get("name") or event.get("target") or "")
        if name.startswith(prefixes):
            return {
                "result": "DENY",
                "reason": f"Least privilege: personal account connector '{name}' is not allowed in the CRUCIBLE lab.",
            }
        return None

    return evaluate
