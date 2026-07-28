"""
TravelMind Agent — 环境预检脚本

在启动后端之前快速验证环境就绪，输出 PASS/FAIL 报告。
避免「后端启动成功但 API 全 404 / LLM 不可用 / 端口冲突」等问题。

用法:
    python scripts/preflight_check.py
    python scripts/preflight_check.py --json   # JSON 格式输出
    python scripts/preflight_check.py --base-url http://staging:8000

退出码:
    0 = 全部通过（含 WARN）
    1 = 有 FAIL 项
"""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ── Constants ─────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "http://localhost:8000"
MIN_ROUTES = 20
EXPECTED_ROUTES_PREFIX = "/api/v1"


# Keys that are "required" (without them, key features break)
REQUIRED_ENV_KEYS = {
    "DEEPSEEK_API_KEY": "LLM 推理（画像提取/行程生成/推荐）",
    "MOONSHOT_API_KEY": "视觉识别（图片分析）",
}

# Keys that are optional (graceful degradation)
OPTIONAL_ENV_KEYS = {
    "AMAP_API_KEY": "高德地图 POI 验证 + 路线优化（缺省：KB-only 模式）",
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    severity: str = "PASS"  # PASS, WARN, FAIL, INFO, SKIP

    def to_dict(self) -> dict:
        return {"name": self.name, "severity": self.severity, "passed": self.passed, "message": self.message}


@dataclass
class PreflightReport:
    results: List[CheckResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    def summary(self) -> dict:
        counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "INFO": 0, "SKIP": 0}
        for r in self.results:
            sev = r.severity
            # "passed" overrides: a PASS result with passed=False → reclassify
            if sev in counts:
                counts[sev] += 1
        return counts

    def exit_code(self) -> int:
        return 1 if self.summary().get("FAIL", 0) > 0 else 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary(),
            "exit_code": self.exit_code(),
        }


# ── Check Functions ───────────────────────────────────────

def check_port_8000(report: PreflightReport, base_url: str) -> None:
    """Check if port 8000 is available. If occupied, identify the process."""
    host = "127.0.0.1"
    port = 8000

    try:
        # Extract port from base_url if different
        if ":" in base_url:
            port_part = base_url.split(":")[-1]
            if port_part.isdigit():
                port = int(port_part)
    except (ValueError, IndexError):
        pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex((host, port))
    sock.close()

    if result != 0:
        report.add(CheckResult(
            name="PORT_AVAILABLE",
            passed=True,
            severity="PASS",
            message=f"端口 {port} 空闲",
        ))
        return

    # Port is occupied — try to identify the process
    process_info = ""
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output(
                f'netstat -ano | findstr :{port} | findstr LISTEN',
                shell=True, timeout=5, stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace").strip()
            lines = [l.strip() for l in output.split("\n") if l.strip()]
            if lines:
                parts = lines[0].split()
                pid = parts[-1] if parts else "?"
                try:
                    pid_info = subprocess.check_output(
                        f'tasklist //FI "PID eq {pid}"',
                        shell=True, timeout=5, stderr=subprocess.DEVNULL
                    ).decode("gbk", errors="replace").strip()
                    process_info = f"（{pid_info.split(chr(10))[3].strip() if len(pid_info.split(chr(10))) > 3 else pid}）"
                except Exception:
                    process_info = f"（PID: {pid}）"
        else:
            output = subprocess.check_output(
                f'lsof -i :{port} 2>/dev/null || ss -tlnp | grep :{port}',
                shell=True, timeout=5, stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace").strip()
            process_info = output[:120] if output else ""
    except Exception:
        process_info = "（无法识别进程）"

    report.add(CheckResult(
        name="PORT_AVAILABLE",
        passed=True,  # WARN 不触发 FAIL
        severity="WARN",
        message=f"端口 {port} 已被占用 {process_info}——请确保这是 TravelMind 后端进程",
    ))


def check_env_vars(report: PreflightReport) -> None:
    """Check environment variables against .env.example."""
    env_path = ROOT_DIR / ".env"
    env_example_path = ROOT_DIR / ".env.example"

    # Read current env
    env_vars: dict = {}
    if env_path.exists():
        with open(env_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                env_vars[key.strip()] = val.strip().strip('"').strip("'")
    else:
        # Fall back to os.environ
        for k in list(REQUIRED_ENV_KEYS) + list(OPTIONAL_ENV_KEYS):
            if os.environ.get(k):
                env_vars[k] = os.environ[k]

    if not env_vars:
        report.add(CheckResult(
            name="ENV_KEYS",
            passed=False,
            severity="FAIL",
            message="未找到 .env 文件，请复制 backend/.env.example 为 backend/.env 并填入真实 Key",
        ))
        return

    # Check required keys
    missing_required = []
    placeholder_required = []
    for key, desc in REQUIRED_ENV_KEYS.items():
        val = env_vars.get(key, "")
        if not val:
            missing_required.append(f"{key}（{desc}）")
        elif val.startswith("sk-") and len(val) < 20:
            placeholder_required.append(f"{key}（{desc}）→ 看起来是占位符，需要填入真实 Key")

    # Check optional keys
    missing_optional = []
    for key, desc in OPTIONAL_ENV_KEYS.items():
        if not env_vars.get(key, ""):
            missing_optional.append(f"{key}（{desc}）")

    total_keys = len(env_vars)
    if missing_required:
        report.add(CheckResult(
            name="ENV_KEYS",
            passed=False,
            severity="FAIL",
            message=f"缺少关键 Key: {'; '.join(missing_required)}",
        ))
    elif placeholder_required:
        report.add(CheckResult(
            name="ENV_KEYS",
            passed=True,
            severity="WARN",
            message=f"{'; '.join(placeholder_required)}",
        ))
    else:
        report.add(CheckResult(
            name="ENV_KEYS",
            passed=True,
            severity="PASS",
            message=f"关键 Key 就绪（{total_keys} 个已配置）",
        ))

    if missing_optional:
        report.add(CheckResult(
            name="ENV_OPTIONAL",
            passed=True,
            severity="INFO",
            message=f"可选 Key 未配置: {'; '.join(missing_optional)}（功能会降级运行）",
        ))


def check_backend_health(report: PreflightReport, base_url: str) -> None:
    """Check that the backend health endpoint responds correctly."""
    import urllib.request
    import json as _json

    url = f"{base_url}/api/v1/health"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read().decode())
            api_status = data.get("services", {}).get("api", "")
            db_status = data.get("services", {}).get("database", "")
            if api_status == "healthy":
                msg = f"API 健康，数据库={db_status}"
                if db_status != "healthy":
                    report.add(CheckResult(name="BACKEND_HEALTH", passed=True, severity="WARN",
                                           message=f"后端在线但数据库异常: {db_status}"))
                else:
                    report.add(CheckResult(name="BACKEND_HEALTH", passed=True, severity="PASS",
                                           message=msg))
            else:
                report.add(CheckResult(name="BACKEND_HEALTH", passed=False, severity="FAIL",
                                       message=f"后端状态异常: {data.get('status', 'unknown')}"))
    except urllib.error.HTTPError as e:
        report.add(CheckResult(name="BACKEND_HEALTH", passed=False, severity="FAIL",
                               message=f"后端返回 HTTP {e.code}"))
    except urllib.error.URLError as e:
        report.add(CheckResult(name="BACKEND_HEALTH", passed=False, severity="FAIL",
                               message=f"后端不可达: {e.reason}（请确认后端已启动）"))
    except Exception as e:
        report.add(CheckResult(name="BACKEND_HEALTH", passed=False, severity="FAIL",
                               message=f"健康检查失败: {e}"))


def check_api_routes(report: PreflightReport, base_url: str) -> None:
    """Check OpenAPI schema and route count."""
    import urllib.request
    import json as _json

    url = f"{base_url}/openapi.json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            schema = _json.loads(resp.read().decode())
            paths = schema.get("paths", {})
            path_count = len(paths)

            # Verify prefix
            prefixed = sum(1 for p in paths if p.startswith(EXPECTED_ROUTES_PREFIX))

            if path_count >= MIN_ROUTES and prefixed == path_count:
                report.add(CheckResult(name="API_ROUTES", passed=True, severity="PASS",
                                       message=f"{path_count} 条路由已验证（全部在 {EXPECTED_ROUTES_PREFIX} 下）"))
            elif path_count < MIN_ROUTES:
                report.add(CheckResult(name="API_ROUTES", passed=False, severity="WARN",
                                       message=f"路由数 {path_count} < 期望 {MIN_ROUTES}——可能是别的服务占用了端口？"))
            elif prefixed < path_count:
                report.add(CheckResult(name="API_ROUTES", passed=False, severity="FAIL",
                                       message=f"{path_count-prefixed} 条路由不在 {EXPECTED_ROUTES_PREFIX} 下——后端版本不对？"))
    except Exception as e:
        report.add(CheckResult(name="API_ROUTES", passed=False, severity="FAIL",
                               message=f"OpenAPI schema 不可达: {e}"))


def check_rag_data(report: PreflightReport) -> None:
    """Check if RAG data files exist."""
    data_dir = ROOT_DIR / "data"
    attractions_file = data_dir / "attractions.json"

    if not data_dir.exists():
        report.add(CheckResult(name="RAG_DATA", passed=False, severity="FAIL",
                               message=f"data/ 目录不存在"))
        return

    if not attractions_file.exists():
        report.add(CheckResult(name="RAG_DATA", passed=False, severity="FAIL",
                               message=f"data/attractions.json 不存在——RAG 无法初始化"))
        return

    try:
        import json as _json
        with open(attractions_file, encoding="utf-8") as f:
            data = _json.load(f)
        count = len(data) if isinstance(data, list) else len(data.get("attractions", data.get("places", [])))
        report.add(CheckResult(name="RAG_DATA", passed=True, severity="PASS",
                               message=f"data/attractions.json 存在（{count} 条 POI）"))
    except Exception as e:
        report.add(CheckResult(name="RAG_DATA", passed=False, severity="FAIL",
                               message=f"data/attractions.json 解析失败: {e}"))

    chroma_dir = ROOT_DIR / "chroma_data"
    if not chroma_dir.exists():
        report.add(CheckResult(name="CHROMA_STORE", passed=True, severity="WARN",
                               message="chroma_data/ 目录不存在（首次启动会由 entrypoint 自举）"))


def check_database_connectivity(report: PreflightReport) -> None:
    """Check database connectivity (optional — only if DATABASE_URL is set)."""
    env_path = ROOT_DIR / ".env"
    db_url = os.environ.get("DATABASE_URL", "")

    if not db_url and env_path.exists():
        with open(env_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    db_url = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not db_url:
        report.add(CheckResult(name="DB_CONNECT", passed=True, severity="SKIP",
                               message="DATABASE_URL 未配置，跳过"))
        return

    # Extract host info for display (sanitize password)
    display_url = db_url.split("@")[-1] if "@" in db_url else db_url
    display_url = display_url.split("?")[0]

    try:
        import asyncio
        async def _try_connect():
            try:
                from sqlalchemy.ext.asyncio import create_async_engine
                engine = create_async_engine(db_url, connect_args={"timeout": 3})
                async with engine.connect() as conn:
                    await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
                await engine.dispose()
                return True, None
            except Exception as e:
                return False, str(e)

        ok, err = asyncio.run(_try_connect())
        if ok:
            report.add(CheckResult(name="DB_CONNECT", passed=True, severity="PASS",
                                   message=f"数据库可达（{display_url}）"))
        else:
            report.add(CheckResult(name="DB_CONNECT", passed=True, severity="WARN",
                                   message=f"数据库不可达: {err[:100]}（部分功能会降级）"))
    except ImportError:
        report.add(CheckResult(name="DB_CONNECT", passed=True, severity="SKIP",
                               message="sqlalchemy 未安装，跳过数据库检查"))


def check_postgres_container(report: PreflightReport) -> None:
    """Check if PostgreSQL Docker container is running (if Docker is available)."""
    try:
        output = subprocess.check_output(
            "docker ps --format '{{.Names}}' 2>/dev/null | grep -i postgres || true",
            shell=True, timeout=5, stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace").strip()
        if output:
            report.add(CheckResult(name="DOCKER_PG", passed=True, severity="INFO",
                                   message=f"PostgreSQL 容器运行中: {output}"))
    except Exception:
        pass  # Docker not available, skip silently


# ── Main ──────────────────────────────────────────────────

def run_all(base_url: str = DEFAULT_BASE_URL) -> PreflightReport:
    """Run all pre-flight checks and return the report."""
    report = PreflightReport()

    print("╔══════════════════════════════════════════════╗")
    print("║     TravelMind Pre-Flight Check             ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # 1. Port availability
    print(f"  🔍 检查端口占用...")
    check_port_8000(report, base_url)

    # 2. Environment variables
    print(f"  🔍 检查环境变量...")
    check_env_vars(report)

    # 3. Backend health
    print(f"  🔍 检查后端健康...")
    check_backend_health(report, base_url)

    # 4. API routes
    print(f"  🔍 检查 API 路由...")
    check_api_routes(report, base_url)

    # 5. RAG data
    print(f"  🔍 检查 RAG 数据...")
    check_rag_data(report)

    # 6. Database
    print(f"  🔍 检查数据库...")
    check_database_connectivity(report)

    # 7. Docker Postgres
    check_postgres_container(report)

    # ── Print results ──
    print()
    print(f"{'='*46}")
    for r in report.results:
        icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "INFO": "ℹ️ ", "SKIP": "⏭️ "}.get(r.severity, "❓")
        print(f"  {icon} [{r.severity}] {r.name}: {r.message}")

    counts = report.summary()
    print()
    print(f"{'='*46}")
    print(f"  结果: {counts.get('PASS',0)} PASS / {counts.get('WARN',0)} WARN "
          f"/ {counts.get('FAIL',0)} FAIL / {counts.get('INFO',0)} INFO / {counts.get('SKIP',0)} SKIP")
    print(f"{'='*46}")

    return report


def main():
    parser = argparse.ArgumentParser(description="TravelMind 环境预检")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"后端 URL（默认 {DEFAULT_BASE_URL}）")
    args = parser.parse_args()

    report = run_all(base_url=args.base_url)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

    sys.exit(report.exit_code())


if __name__ == "__main__":
    main()
