"""Tile fountain — tile generation with rate limiting, priority queue, and backpressure."""
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import deque
from enum import Enum

class TilePriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

@dataclass
class TileRequest:
    content: str
    domain: str = "general"
    priority: TilePriority = TilePriority.NORMAL
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    filled_at: float = 0.0
    id: str = ""

@dataclass
class FountainConfig:
    rate_limit: float = 10.0  # tiles per second
    burst_size: int = 5
    max_queue: int = 1000
    backpressure_threshold: float = 0.8  # start throttling at 80% queue

class TileFountain:
    def __init__(self, config: FountainConfig = None):
        self.config = config or FountainConfig()
        self._queue: deque = deque(maxlen=self.config.max_queue)
        self._history: list[TileRequest] = []
        self._tokens: float = self.config.burst_size
        self._last_refill: float = time.time()
        self._total_generated: int = 0
        self._total_dropped: int = 0
        self._domain_counts: dict[str, int] = {}
        self._request_counter: int = 0

    def request(self, content: str, domain: str = "", priority: str = "normal",
                confidence: float = 0.5, tags: list[str] = None) -> Optional[TileRequest]:
        self._refill_tokens()
        if self._tokens < 1.0 and self.config.rate_limit > 0:
            self._total_dropped += 1
            return None  # rate limited
        if len(self._queue) >= int(self.config.max_queue * self.config.backpressure_threshold):
            self._total_dropped += 1
            return None  # backpressure
        req = TileRequest(content=content, domain=domain or "general",
                         priority=TilePriority[priority.upper()] if isinstance(priority, str) else priority,
                         confidence=confidence, tags=tags or [],
                         id=f"req-{self._request_counter}")
        self._request_counter += 1
        # Insert by priority
        inserted = False
        for i, existing in enumerate(self._queue):
            if req.priority.value > existing.priority.value:
                self._queue.insert(i, req)
                inserted = True
                break
        if not inserted:
            self._queue.append(req)
        self._tokens -= 1
        self._domain_counts[domain or "general"] = self._domain_counts.get(domain or "general", 0) + 1
        return req

    def emit(self, count: int = 1) -> list[TileRequest]:
        results = []
        for _ in range(min(count, len(self._queue))):
            if self._queue:
                req = self._queue.popleft()
                req.filled_at = time.time()
                self._history.append(req)
                self._total_generated += 1
                results.append(req)
        if len(self._history) > 5000:
            self._history = self._history[-5000:]
        return results

    def peek(self, n: int = 10) -> list[TileRequest]:
        return list(self._queue)[:n]

    def drain(self) -> list[TileRequest]:
        results = list(self._queue)
        self._queue.clear()
        now = time.time()
        for r in results:
            r.filled_at = now
            self._history.append(r)
            self._total_generated += 1
        return results

    def _refill_tokens(self):
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(self.config.burst_size, self._tokens + elapsed * self.config.rate_limit)
        self._last_refill = now

    def set_rate_limit(self, rate: float, burst: int = 5):
        self.config.rate_limit = rate
        self.config.burst_size = burst

    def queue_depth(self, domain: str = "") -> int:
        if domain:
            return sum(1 for r in self._queue if r.domain == domain)
        return len(self._queue)

    @property
    def tokens_available(self) -> float:
        self._refill_tokens()
        return self._tokens

    @property
    def stats(self) -> dict:
        return {"queue_depth": len(self._queue), "total_generated": self._total_generated,
                "total_dropped": self._total_dropped, "tokens": round(self._tokens, 2),
                "rate_limit": self.config.rate_limit, "burst": self.config.burst_size,
                "domains": dict(self._domain_counts),
                "drop_rate": round(self._total_dropped / max(self._total_generated + self._total_dropped, 1), 3)}
