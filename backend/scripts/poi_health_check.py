"""
TravelMind Agent — POI 存续自动巡检

遍历知识库全部 POI（从 backend/data/attractions.json 读取），通过高德
POI 搜索 API 逐条验证存续状态，输出巡检报告（backend/data/poi_health_YYYY-MM-DD.json）。

分类规则：
  - active:     高德搜索有名称匹配命中 → POI 存续
  - inactive:   高德搜索无匹配结果 → POI 可能已关闭/下架
  - uncertain:  API 调用失败（网络/限流），状态无法确认
  - unverified: POI 没有 amap_id，无法通过高德验证

速率控制：asyncio.Semaphore(5)，远低于免费配额 30 QPS / 5000 calls/day。

零硬编码：POI 列表全部来自 data 文件，脚本内不含任何城市名或景点名常量。

Usage:
  cd backend
  python scripts/poi_health_check.py
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 脚本可从项目根或 backend/ 目录运行 — 确保 app 包在 sys.path 中
_THIS_FILE = Path(__file__).resolve()
_BACKEND_DIR = _THIS_FILE.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config.settings import settings
from app.services.amap_service import search_poi
from app.agents.route_optimizer import (
    _base_name,
    _core_name,
    _normalize,
    _name_matches,
    _INFRA_RE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("poi_health_check")

# ── Paths ──────────────────────────────────────────────────

DATA_DIR = _BACKEND_DIR / "data"
ATTRACTIONS_PATH = DATA_DIR / "attractions.json"

# ── Constants ──────────────────────────────────────────────

MAX_CONCURRENCY = 5  # 并发数，远低于 Amap 30 QPS 限制


# ── Helpers ────────────────────────────────────────────────


def _load_attractions() -> List[Dict[str, Any]]:
    """从 attractions.json 加载全部 POI（零硬编码 POI 列表）。"""
    if not ATTRACTIONS_PATH.exists():
        logger.error(f"Attractions file not found: {ATTRACTIONS_PATH}")
        sys.exit(1)

    with open(ATTRACTIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data.get("attractions", [])
    logger.info(f"Loaded {len(attractions)} attractions from {ATTRACTIONS_PATH}")
    return attractions


def _poi_has_amap(poi: Dict[str, Any]) -> bool:
    """是否有 amap_id 可用于高德验证。"""
    return bool(poi.get("amap_id"))


async def _check_one(
    sem: asyncio.Semaphore,
    poi: Dict[str, Any],
) -> Dict[str, Any]:
    """对单条 POI 执行高德存续检查。

    返回结果字典，必定包含 status (active|inactive|uncertain)。
    """
    name = poi.get("name", "")
    city = poi.get("city", "")
    amap_id = poi.get("amap_id", "")

    base_name = _base_name(name)
    result = {
        "name": name,
        "city": city,
        "lat": poi.get("lat"),
        "lon": poi.get("lon"),
        "amap_id": amap_id,
    }

    async with sem:
        try:
            hits = await search_poi(base_name, city, limit=5)
        except Exception as e:
            logger.debug(f"API error for '{name}' ({city}): {e}")
            result["status"] = "uncertain"
            result["reason"] = str(e)[:200]
            return result

    if not hits:
        result["status"] = "inactive"
        result["reason"] = f"高德搜索 '{base_name}' @ '{city}' 无匹配结果"
        return result

    # 过滤基础设施命中
    valid_hits = [h for h in hits if not _INFRA_RE.search(h.get("name", ""))]

    # 名称匹配
    for h in valid_hits:
        if _name_matches(base_name, h.get("name", "")):
            result["status"] = "active"
            result["matched_name"] = h.get("name", "")
            result["matched_adname"] = h.get("adname", "")
            result["matched_address"] = h.get("address", "")
            return result

    # 有结果但无名称匹配 → 可能改名或下架
    result["status"] = "inactive"
    result["reason"] = (
        f"高德搜索 '{base_name}' @ '{city}' 返回 {len(valid_hits)} 条结果，"
        f"但无名称匹配（最近命中: {valid_hits[0].get('name', 'N/A') if valid_hits else 'N/A'}）"
    )
    return result


async def _check_all(
    pois: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """并发检查全部有 amap_id 的 POI。

    Returns:
        (all_results, summary):
        - all_results: 每条 POI 的详细结果
        - summary: {total_checked, active, inactive, uncertain, unverified, api_errors}
    """
    # 分类：有 amap_id 的走 API 验证，没有的标记 unverified
    checkable = [p for p in pois if _poi_has_amap(p)]
    unverifiable = [p for p in pois if not _poi_has_amap(p)]

    logger.info(
        f"Checkable (has amap_id): {len(checkable)}, "
        f"Unverifiable (no amap_id): {len(unverifiable)}"
    )

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    # 分批并发
    results: List[Dict[str, Any]] = []
    for i in range(0, len(checkable), MAX_CONCURRENCY * 2):
        batch = checkable[i : i + MAX_CONCURRENCY * 2]
        tasks = [_check_one(sem, p) for p in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, r in enumerate(batch_results):
            if isinstance(r, Exception):
                results.append({
                    "name": batch[j].get("name", ""),
                    "city": batch[j].get("city", ""),
                    "lat": batch[j].get("lat"),
                    "lon": batch[j].get("lon"),
                    "amap_id": batch[j].get("amap_id", ""),
                    "status": "uncertain",
                    "reason": str(r)[:200],
                })
            else:
                results.append(r)

        if i + MAX_CONCURRENCY * 2 < len(checkable):
            logger.info(f"Progress: {min(i + MAX_CONCURRENCY * 2, len(checkable))}/{len(checkable)}")

    # 添加 unverifiable POI
    for p in unverifiable:
        results.append({
            "name": p.get("name", ""),
            "city": p.get("city", ""),
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "amap_id": None,
            "status": "unverified",
            "reason": "POI 缺少 amap_id，无法通过高德验证",
        })

    # 汇总统计
    summary = {
        "total_checked": len(checkable),
        "active": sum(1 for r in results if r["status"] == "active"),
        "inactive": sum(1 for r in results if r["status"] == "inactive"),
        "uncertain": sum(1 for r in results if r["status"] == "uncertain"),
        "unverified": len(unverifiable),
        "api_errors": sum(1 for r in results if r["status"] == "uncertain"),
    }

    return results, summary


def _write_report(
    results: List[Dict[str, Any]],
    summary: Dict[str, int],
) -> Path:
    """写入巡检报告到 data/poi_health_YYYY-MM-DD.json。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"poi_health_{today}.json"

    # 提取 inactive POI 摘要
    inactive_pois = [
        {
            "name": r["name"],
            "city": r["city"],
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "amap_id": r.get("amap_id"),
            "status": r["status"],
            "reason": r.get("reason", ""),
        }
        for r in results
        if r["status"] == "inactive"
    ]

    report = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(ATTRACTIONS_PATH),
        "source_poi_count": len(results),
        "summary": summary,
        "inactive_pois": inactive_pois,
        "all_results": sorted(
            results,
            key=lambda x: ({"active": 0, "inactive": 1, "uncertain": 2, "unverified": 3}[x["status"]], x["name"]),
        ),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"Report written: {out_path}")
    return out_path


# ── Main ───────────────────────────────────────────────────


async def main():
    """主入口：加载 → 检查 → 输出报告。"""
    # 验证 API Key
    if not settings.AMAP_API_KEY:
        logger.error("AMAP_API_KEY not configured — cannot run health check")
        sys.exit(1)

    logger.info("=== TravelMind POI Health Check ===")
    logger.info("Amap API Key: *** (configured)")
    logger.info(f"Concurrency: {MAX_CONCURRENCY}")

    # 1. 加载 POI（零硬编码）
    pois = _load_attractions()

    # 2. 并发检查
    logger.info(f"Starting health check for {len(pois)} POIs...")
    results, summary = await _check_all(pois)

    # 3. 输出报告
    out_path = _write_report(results, summary)

    # 4. 打印摘要
    print("\n" + "=" * 60)
    print("  POI HEALTH CHECK SUMMARY")
    print("=" * 60)
    print(f"  Total POIs:      {len(pois):>5}")
    print(f"  Checked (Amap):  {summary['total_checked']:>5}")
    print(f"  ✅ Active:       {summary['active']:>5}  ({_pct(summary['active'], len(pois))}%)")
    print(f"  ❌ Inactive:     {summary['inactive']:>5}  ({_pct(summary['inactive'], len(pois))}%)")
    print(f"  ⚠️  Uncertain:    {summary['uncertain']:>5}")
    print(f"  ➖ Unverified:   {summary['unverified']:>5}")
    print(f"  📄 Report:       {out_path}")
    print("=" * 60)

    # 列出 inactive POI
    inactive_pois = [r for r in results if r["status"] == "inactive"]
    if inactive_pois:
        print(f"\n  ⚠️  {len(inactive_pois)} INACTIVE POIs:")
        for p in inactive_pois[:20]:  # 最多打印 20 条
            print(f"    - {p['name']} ({p['city']}): {p.get('reason', '')[:80]}")
        if len(inactive_pois) > 20:
            print(f"    ... and {len(inactive_pois) - 20} more (see report)")

    return 0


def _pct(part: int, total: int) -> str:
    """计算百分比，total 为 0 时返回 0.0。"""
    if total == 0:
        return "0.0"
    return f"{part / total * 100:.1f}"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
