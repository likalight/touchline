"""Bound expensive public work without retaining visitor identifiers.

Limits are process-local: the deployment currently has one replica. They are not
a currency budget; Azure billing alerts and a shared quota store are still needed
before scaling replicas. Requests are rejected rather than queued indefinitely.
"""
from collections import deque
import time

from starlette.responses import JSONResponse


class WorkBudget:
    def __init__(self, maximum=60, window=60, concurrency=4, clock=time.monotonic):
        self.maximum, self.window, self.concurrency = maximum, window, concurrency
        self.clock = clock
        self.starts = deque()
        self.active = self.rejected = 0

    def acquire(self):
        now = self.clock()
        while self.starts and self.starts[0] <= now - self.window:
            self.starts.popleft()
        if self.active >= self.concurrency or len(self.starts) >= self.maximum:
            self.rejected += 1
            return False
        self.starts.append(now)
        self.active += 1
        return True

    def release(self):
        self.active = max(0, self.active - 1)

    def status(self):
        return {"maximum": self.maximum, "window_seconds": self.window,
                "concurrency": self.concurrency, "active": self.active,
                "rejected": self.rejected, "scope": "single process"}


class PublicWorkLimits:
    """ASGI guard also covers direct A2A/MCP requests; no forwarded-IP trust."""
    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        self.budgets = {"model": WorkBudget(60, 60, 4),
                        "speech": WorkBudget(60, 60, 3),
                        "scenario": WorkBudget(12, 60, 2),
                        "reel": WorkBudget(3, 60, 1),
                        "session": WorkBudget(12, 60, 2)}

    @staticmethod
    def category(path, method):
        if method == "POST" and (path in ("/a2a", "/mcp", "/mcp/") or path.endswith("/ask")):
            return "model"
        if path == "/api/speak":
            return "speech"
        if method == "POST":
            if path.endswith("/whatif"):
                return "scenario"
            if path.endswith("/reel"):
                return "reel"
            if path in ("/api/judge", "/api/matches"):
                return "session"
        if path.endswith("/recap"):
            return "model"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            self.reset()
        category = self.category(scope.get("path", ""), scope.get("method", "")) if scope["type"] == "http" else None
        if category is None:
            return await self.app(scope, receive, send)
        budget = self.budgets[category]
        if not budget.acquire():
            return await JSONResponse({"detail": "This demo is busy. Please try again shortly.",
                                       "reason": "capacity_limit"}, status_code=429,
                                      headers={"Retry-After": str(budget.window)})(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            budget.release()
