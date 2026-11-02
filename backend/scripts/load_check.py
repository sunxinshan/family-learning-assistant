"""Small read-only concurrency check for deployment smoke testing."""

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--nickname", default="Alice")
    parser.add_argument("--password", default="demo123")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        login = client.post(
            "/auth/login", json={"nickname": args.nickname, "password": args.password}
        )
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        paths = ["/health/live", "/tasks", "/learning/stats"]
        latencies: list[float] = []
        failures = 0

        def request(index: int) -> None:
            nonlocal failures
            started = time.perf_counter()
            try:
                response = client.get(paths[index % len(paths)], headers=headers)
                if response.status_code >= 400:
                    failures += 1
            except httpx.HTTPError:
                failures += 1
            finally:
                latencies.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            list(executor.map(request, range(args.requests)))
        elapsed = time.perf_counter() - started

    payload = {
        "requests": args.requests,
        "concurrency": args.concurrency,
        "elapsedSeconds": round(elapsed, 3),
        "requestsPerSecond": round(args.requests / elapsed, 2) if elapsed else 0,
        "errorRate": round(failures / max(args.requests, 1) * 100, 2),
        "latencyP50Ms": round(percentile(latencies, 0.50), 2),
        "latencyP95Ms": round(percentile(latencies, 0.95), 2),
        "latencyP99Ms": round(percentile(latencies, 0.99), 2),
        "latencyMeanMs": round(statistics.fmean(latencies), 2) if latencies else 0,
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
