"""BrokerMetrics: what a Broker reports about itself. Written by the Broker's
own thread, read by the admin."""

import threading
from collections import deque
from typing import Any

OUTCOMES = ("served", "lost", "failed")


def _whole(count: object, what: str) -> int:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"{what} must be a whole number, 0 or more")
    return count


class BrokerMetrics:
    """Counters and latency. Safe to use from several threads: the Broker thread
    writes and the admin's request threads read.

    Latency: the count, mean and maximum cover everything since the start. The
    95th percentile covers only the most recent `window` requests, so it shows
    how the Broker is doing now, not how it did an hour ago.
    """

    def __init__(self, window: int = 200) -> None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ValueError("window must be a whole number of at least 1")
        self._lock = threading.Lock()
        self._counts = {name: 0 for name in OUTCOMES}
        self._recent: deque[float] = deque(maxlen=window)
        self._total_ms = 0.0
        self._max_ms = 0.0
        self._count = 0
        self._pending = 0
        self._recovered = 0

    def record(self, milliseconds: float, outcome: str) -> None:
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
        if milliseconds < 0:
            raise ValueError("milliseconds must not be negative")
        with self._lock:
            self._counts[outcome] += 1
            self._count += 1
            self._total_ms += milliseconds
            self._max_ms = max(self._max_ms, milliseconds)
            self._recent.append(milliseconds)

    def set_pending(self, count: int) -> None:
        with self._lock:
            self._pending = _whole(count, "count")

    def set_recovered(self, count: int) -> None:
        with self._lock:
            self._recovered = _whole(count, "count")

    def snapshot(self) -> dict[str, Any]:
        """A copy of everything, as plain numbers."""
        with self._lock:
            recent = sorted(self._recent)
            # The 95th percentile: the value that 95 in 100 requests were faster than.
            p95 = recent[(95 * len(recent) + 99) // 100 - 1] if recent else 0.0
            mean = self._total_ms / self._count if self._count else 0.0
            return {
                "requests_served": self._counts["served"],
                "requests_lost_connection": self._counts["lost"],
                "requests_failed": self._counts["failed"],
                "pending_operations": self._pending,
                "recovered_at_start": self._recovered,
                "latency_ms": {
                    "count": self._count,
                    "mean": round(mean, 1),
                    "max": round(self._max_ms, 1),
                    "p95": round(p95, 1),
                },
            }