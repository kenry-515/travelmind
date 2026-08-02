"""
TravelMind Agent — 自实现轻量 metrics 中间件 (Phase 18 P3 + P4)

Phase 18 P4: Redis 跨 worker 聚合
- record_request: 本地记录 + async 推 Redis (fire-and-forget)
- render: 本地 metrics (单 worker 视图)
- render_with_redis: 合并 Redis 数据 (跨 worker 视图)
"""

import asyncio
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, Optional, Tuple


class MetricsStore:
    """线程安全的 metrics 存储 (单进程足够, 多进程需用 Redis 聚合)。"""

    def __init__(self):
        self._lock = Lock()
        self._started_at: float = time.time()
        self._stopped_at: float = 0.0
        self._requests: Dict[Tuple[str, str, int], int] = defaultdict(int)
        self._durations: Dict[Tuple[str, str], float] = defaultdict(float)
        self._max_durations: Dict[Tuple[str, str], float] = defaultdict(float)
        self._status_counts: Dict[int, int] = defaultdict(int)

    def mark_started(self):
        with self._lock:
            self._started_at = time.time()
            self._stopped_at = 0.0

    def mark_stopped(self):
        with self._lock:
            self._stopped_at = time.time()

    def record_request(self, method: str, path: str, status: int, duration: float):
        """记录一次请求 (本地 + 异步推 Redis)。"""
        with self._lock:
            self._requests[(method, path, status)] += 1
            self._durations[(method, path)] += duration
            if duration > self._max_durations[(method, path)]:
                self._max_durations[(method, path)] = duration
            self._status_counts[status] += 1

        # Async push to Redis (fire-and-forget, optional)
        try:
            from app.middleware.redis_metrics import get_redis_metrics_backend
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._record_redis(method, path, status, duration))
                else:
                    asyncio.run(self._record_redis(method, path, status, duration))
            except RuntimeError:
                # No event loop
                pass
        except Exception:
            pass

    async def _record_redis(self, method: str, path: str, status: int, duration: float):
        backend = await get_redis_metrics_backend()
        if backend:
            await backend.increment(method, path, status, duration)

    def _build_prometheus_output(
        self,
        requests_data: Dict[Tuple[str, str, int], int],
        durations_data: Dict[Tuple[str, str], float],
        max_durations_data: Dict[Tuple[str, str], float],
        status_counts_data: Dict[int, int],
        uptime: float,
        suffix: str = "",
    ) -> str:
        """构造 Prometheus 文本格式 (suffix 用于 Redis-aggregated 区分)。"""
        lines = [
            "# HELP travelmind_uptime_seconds Service uptime",
            "# TYPE travelmind_uptime_seconds gauge",
            f"travelmind_uptime_seconds {uptime:.2f}",
            "",
            f"# HELP travelmind_requests_total Total HTTP requests{suffix}",
            "# TYPE travelmind_requests_total counter",
        ]
        for (method, path, status), count in sorted(requests_data.items()):
            path_escaped = path.replace('"', '\\"')
            lines.append(
                f'travelmind_requests_total{{method="{method}",path="{path_escaped}",status="{status}"}} {count}'
            )

        lines.extend([
            "",
            f"# HELP travelmind_request_duration_seconds HTTP request duration{suffix}",
            "# TYPE travelmind_request_duration_seconds summary",
        ])
        for (method, path), total_dur in sorted(durations_data.items()):
            count = sum(
                c for (m, p, s), c in requests_data.items()
                if m == method and p == path
            )
            path_escaped = path.replace('"', '\\"')
            lines.extend([
                f'travelmind_request_duration_seconds_sum{{method="{method}",path="{path_escaped}"}} {total_dur:.6f}',
                f'travelmind_request_duration_seconds_count{{method="{method}",path="{path_escaped}"}} {count}',
            ])

        lines.extend([
            "",
            f"# HELP travelmind_http_responses_total HTTP response count by status{suffix}",
            "# TYPE travelmind_http_responses_total counter",
        ])
        for status, count in sorted(status_counts_data.items()):
            lines.append(
                f'travelmind_http_responses_total{{status="{status}"}} {count}'
            )

        return "\n".join(lines) + "\n"

    def render(self) -> str:
        """渲染 Prometheus 文本格式 metrics (本地)。"""
        with self._lock:
            uptime = (self._stopped_at or time.time()) - self._started_at
            return self._build_prometheus_output(
                dict(self._requests),
                dict(self._durations),
                dict(self._max_durations),
                dict(self._status_counts),
                uptime,
            )

    async def render_with_redis(self) -> str:
        """Render metrics including aggregated Redis data (跨 worker)。"""
        from app.middleware.redis_metrics import get_redis_metrics_backend
        backend = await get_redis_metrics_backend()
        if not backend:
            return self.render()

        agg = await backend.aggregate()
        if not agg:
            return self.render()

        # Use Redis aggregated data
        with self._lock:
            uptime = (self._stopped_at or time.time()) - self._started_at

        # Convert agg dicts to internal format
        requests_data: Dict[Tuple[str, str, int], int] = {}
        for (method, path, status), count in agg.get("requests", {}).items():
            requests_data[(method, path, status)] = count
        durations_data: Dict[Tuple[str, str], float] = {}
        max_durations_data: Dict[Tuple[str, str], float] = {}
        for (method, path), info in agg.get("durations", {}).items():
            durations_data[(method, path)] = info["total"]
            max_durations_data[(method, path)] = info["max"]

        return self._build_prometheus_output(
            requests_data,
            durations_data,
            max_durations_data,
            agg.get("status_counts", {}),
            uptime,
            suffix=" (Redis-aggregated)",
        )


def get_metrics_response() -> str:
    """返回 Prometheus metrics 文本 (sync 接口 for ASGI middleware)。"""
    from app.main import metrics_store
    return metrics_store.render()


async def get_metrics_response_async() -> str:
    """返回 Prometheus metrics 文本 (async 接口 for endpoint)。"""
    from app.main import metrics_store
    return await metrics_store.render_with_redis()