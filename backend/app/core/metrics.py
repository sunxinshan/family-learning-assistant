import threading
from collections import Counter
from typing import Any


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight = 0
        self._total = 0
        self._errors = 0
        self._status_classes: Counter[str] = Counter()
        self._latency_sum_ms = 0.0
        self._latency_max_ms = 0.0

    def request_started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def request_finished(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._total += 1
            if status_code >= 500:
                self._errors += 1
            self._status_classes[f"{status_code // 100}xx"] += 1
            self._latency_sum_ms += duration_ms
            self._latency_max_ms = max(self._latency_max_ms, duration_ms)

    def request_aborted(self, duration_ms: float) -> None:
        self.request_finished(500, duration_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            average = self._latency_sum_ms / self._total if self._total else 0.0
            return {
                "requestsTotal": self._total,
                "errorsTotal": self._errors,
                "inFlight": self._in_flight,
                "statusClasses": dict(self._status_classes),
                "latencyAverageMs": round(average, 2),
                "latencyMaxMs": round(self._latency_max_ms, 2),
            }


metrics = MetricsRegistry()
