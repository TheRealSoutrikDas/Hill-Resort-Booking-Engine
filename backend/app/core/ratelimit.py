"""An in-memory sliding-window rate limiter (A-79, A-82, D-34).

For each key (for example "login_ip:203.0.113.7") it keeps the times of recent hits and
forgets those older than the window. That is exact, with no burst at window edges.

Counts live in this process only: several workers or instances would each count
separately, and a restart resets them. The deployment therefore runs one instance with
one worker (deployment.md); a shared store such as Redis is out of scope (brief).
"""

import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(self, max_keys: int = 10_000, clock: Callable[[], float] = time.monotonic) -> None:
        self._max_keys = max_keys
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()  # routes run on several threads

    def _recent(self, key: str, window_s: float, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            hits = deque()
            self._hits[key] = hits
            if len(self._hits) > self._max_keys:
                # Bounded memory: drop the least recently used key, so a flood of fake
                # IPs cannot grow this without limit.
                self._hits.popitem(last=False)
        else:
            self._hits.move_to_end(key)
        while hits and hits[0] <= now - window_s:
            hits.popleft()
        return hits

    def _retry_after(self, hits: deque[float], window_s: float, now: float) -> int:
        return max(1, math.ceil(hits[0] + window_s - now))

    def hit(self, key: str, limit: int, window_s: float) -> int | None:
        """Count one attempt. Returns None if allowed, else seconds until one is allowed."""
        now = self._clock()
        with self._lock:
            hits = self._recent(key, window_s, now)
            if len(hits) >= limit:
                return self._retry_after(hits, window_s, now)
            hits.append(now)
            return None

    def blocked_for(self, key: str, limit: int, window_s: float) -> int | None:
        """Like `hit`, but only looks: used before a login, whose failures are counted after."""
        now = self._clock()
        with self._lock:
            hits = self._recent(key, window_s, now)
            return self._retry_after(hits, window_s, now) if len(hits) >= limit else None

    def record(self, key: str, window_s: float) -> None:
        now = self._clock()
        with self._lock:
            self._recent(key, window_s, now).append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def __len__(self) -> int:
        return len(self._hits)
