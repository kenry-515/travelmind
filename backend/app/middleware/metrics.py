"""
TravelMind Agent — 自实现轻量 metrics 中间件 (Phase 18 P3)

不依赖 prometheus_client / prometheus_fastapi_instrumentator:
- 完全内置, 启动无依赖
- /metrics 端点返回 Prometheus 文本格式 (兼容 scraper)
- 记录: 请求总数 / endpoint 延迟 / 状态码分布 / 启动时间
"""

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, Tuple


class MetricsStore:
    """线程安全的 metrics 存储 (单进程足够, 多进程需用 prometheus_multiproc_dir)。"""

    def __init__(self):
        self._lock = Lock()
        self._started_at: float = time.time()
        self._stopped_at: float = 0.0
        # (method, path, status) -> count
        self._requests: Dict[Tuple[str, str, int], int] = defaultdict(int)
        # (method, path) -> total duration seconds
        self._durations: Dict[Tuple[str, str], float] = defaultdict(float)
        # (method, path) -> max duration
        self._max_durations: Dict[Tuple[str, str], float] = defaultdict(float)
        # status_code -> count
        self._status_counts: Dict[int, int] = defaultdict(int)

    def mark_started(self):
        with self._lock:
            self._started_at = time.time()
            self._stopped_at = 0.0

    def mark_stopped(self):
        with self._lock:
            self._stopped_at = time.time()

    def record_request(self, method: str, path: str, status: int, duration: float):
        """记录一次请求 (path 是路由模板, e.g., '/api/v1/dialog/message')。"""
        with self._lock:
            self._requests[(method, path, status)] += 1
            self._durations[(method, path)] += duration
            if duration > self._max_durations[(method, path)]:
                self._max_durations[(method, path)] = duration
            self._status_counts[status] += 1

    def render(self) -> str:
        """渲染 Prometheus 文本格式 metrics。"""
        with self._lock:
            uptime = (self._stopped_at or time.time()) - self._started_at
            lines = [
                "# HELP travelmind_uptime_seconds Service uptime",
                "# TYPE travelmind_uptime_seconds gauge",
                f"travelmind_uptime_seconds {uptime:.2f}",
                "",
                "# HELP travelmind_requests_total Total HTTP requests",
                "# TYPE travelmind_requests_total counter",
            ]
            for (method, path, status), count in sorted(self._requests.items()):
                # Prometheus 标签转义
                path_escaped = path.replace('"', '\\"')
                lines.append(
                    f'travelmind_requests_total{{method="{method}",path="{path_escaped}",status="{status}"}} {count}'
                )

            lines.extend([
                "",
                "# HELP travelmind_request_duration_seconds HTTP request duration",
                "# TYPE travelmind_request_duration_seconds summary",
            ])
            for (method, path), total_dur in sorted(self._durations.items()):
                count = sum(
                    c for (m, p, s), c in self._requests.items()
                    if m == method and p == path
                )
                avg = total_dur / count if count else 0
                max_dur = self._max_durations[(method, path)]
                path_escaped = path.replace('"', '\\"')
                lines.extend([
                    f'travelmind_request_duration_seconds_sum{{method="{method}",path="{path_escaped}"}} {total_dur:.6f}',
                    f'travelmind_request_duration_seconds_count{{method="{method}",path="{path_escaped}"}} {count}',
                ])

            lines.extend([
                "",
                "# HELP travelmind_http_responses_total HTTP response count by status",
                "# TYPE travelmind_http_responses_total counter",
            ])
            for status, count in sorted(self._status_counts.items()):
                lines.append(
                    f'travelmind_http_responses_total{{status="{status}"}} {count}'
                )

            return "\n".join(lines) + "\n"


def get_metrics_response() -> str:
    """返回 Prometheus metrics 文本。"""
    from app.main import metrics_store
    return metrics_store.render()