"""Tile fountain — generates tiles from templates with rate limiting, priority queues, cooldowns."""
import time
import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import defaultdict, deque
from enum import Enum

class FountainStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COOLDOWN = "cooldown"
    EMPTY = "empty"

@dataclass
class TileTemplate:
    name: str
    pattern: str          # template string with {variable} placeholders
    variables: dict = field(default_factory=dict)  # variable → list of values
    domain: str = ""
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)

@dataclass
class GeneratedTile:
    id: str
    content: str
    domain: str
    confidence: float
    template: str
    room: str
    tags: list[str]
    generated_at: float = field(default_factory=time.time)

@dataclass
class RateLimit:
    max_per_minute: int = 60
    max_per_hour: int = 1000
    burst_size: int = 10
    cooldown_s: float = 0.0  # per-room cooldown between generations

class TileFountain:
    def __init__(self, rate_limit: RateLimit = None):
        self.rate_limit = rate_limit or RateLimit()
        self._templates: dict[str, TileTemplate] = {}
        self._generators: dict[str, Callable] = {}
        self._room_cooldowns: dict[str, float] = {}
        self._room_counts: dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._room_hourly: dict[str, deque] = defaultdict(lambda: deque(maxlen=100000))
        self._generated: list[GeneratedTile] = []
        self._total_generated: int = 0
        self._status = FountainStatus.ACTIVE

    def add_template(self, template: TileTemplate):
        self._templates[template.name] = template

    def add_generator(self, name: str, fn: Callable):
        self._generators[name] = fn

    def generate(self, template_name: str, room: str = "", variables: dict = None) -> Optional[GeneratedTile]:
        if self._status == FountainStatus.PAUSED:
            return None
        if not self._check_rate(room):
            self._status = FountainStatus.COOLDOWN
            return None
        self._status = FountainStatus.ACTIVE
        template = self._templates.get(template_name)
        if template:
            tile = self._generate_from_template(template, room, variables)
        elif template_name in self._generators:
            tile = self._generators[template_name](room)
            if tile and isinstance(tile, dict):
                tile = GeneratedTile(
                    id=tile.get("id", f"gen-{self._total_generated}"),
                    content=tile["content"], domain=tile.get("domain", ""),
                    confidence=tile.get("confidence", 0.5), template=template_name,
                    room=room, tags=tile.get("tags", []))
            elif tile is None:
                return None
        else:
            return None
        self._generated.append(tile)
        self._total_generated += 1
        self._room_counts[room].append(time.time())
        self._room_hourly[room].append(time.time())
        self._room_cooldowns[room] = time.time()
        return tile

    def generate_batch(self, template_name: str, count: int, room: str = "") -> list[GeneratedTile]:
        results = []
        for _ in range(count):
            tile = self.generate(template_name, room)
            if tile:
                results.append(tile)
            else:
                break  # rate limited
        return results

    def pause(self):
        self._status = FountainStatus.PAUSED

    def resume(self):
        self._status = FountainStatus.ACTIVE

    def room_rate(self, room: str) -> dict:
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600
        per_minute = sum(1 for t in self._room_counts[room] if t >= minute_ago)
        per_hour = sum(1 for t in self._room_hourly[room] if t >= hour_ago)
        return {"per_minute": per_minute, "per_hour": per_hour,
                "limit_minute": self.rate_limit.max_per_minute,
                "limit_hour": self.rate_limit.max_per_hour}

    def templates(self) -> list[TileTemplate]:
        return list(self._templates.values())

    def recent(self, n: int = 20) -> list[GeneratedTile]:
        return self._generated[-n:]

    def by_room(self, room: str, limit: int = 50) -> list[GeneratedTile]:
        return [t for t in self._generated if t.room == room][-limit:]

    def _generate_from_template(self, template: TileTemplate, room: str,
                                overrides: dict = None) -> GeneratedTile:
        vars = {k: random.choice(v) for k, v in template.variables.items()}
        if overrides:
            vars.update(overrides)
        content = template.pattern.format(**vars)
        tile_id = hashlib.md5(f"{template.name}:{content}:{time.time()}".encode()).hexdigest()[:12]
        return GeneratedTile(
            id=tile_id, content=content, domain=template.domain,
            confidence=template.confidence, template=template.name,
            room=room, tags=template.tags
        )

    def _check_rate(self, room: str) -> bool:
        now = time.time()
        # Per-room cooldown
        last = self._room_cooldowns.get(room, 0)
        if self.rate_limit.cooldown_s > 0 and now - last < self.rate_limit.cooldown_s:
            return False
        # Per-minute rate
        minute_ago = now - 60
        per_minute = sum(1 for t in self._room_counts[room] if t >= minute_ago)
        if per_minute >= self.rate_limit.max_per_minute:
            return False
        # Per-hour rate
        hour_ago = now - 3600
        per_hour = sum(1 for t in self._room_hourly[room] if t >= hour_ago)
        if per_hour >= self.rate_limit.max_per_hour:
            return False
        return True

    @property
    def status(self) -> FountainStatus:
        return self._status

    @property
    def stats(self) -> dict:
        return {"templates": len(self._templates), "generators": len(self._generators),
                "total_generated": self._total_generated, "status": self._status.value,
                "rooms_active": len(self._room_counts)}
