"""
TravelMind Agent — Core Constants（Phase 12.29 集中化）

所有跨模块共享的业务常量集中管理，各模块统一从这里导入。
避免 BUDGET_MAP / SEASON_MONTHS 等在三处重复定义。
"""

# ── Budget mapping ───────────────────────────────────────
# 用户输入 → 标准化等级
BUDGET_MAP = {
    "穷游": "经济",
    "经济": "经济",
    "低": "经济",
    "中等": "适中",
    "适中": "适中",
    "舒适": "适中",
    "高端": "高端",
    "奢华": "高端",
    "高": "高端",
}

BUDGET_LEVELS = ["经济", "适中", "高端"]


def normalize_budget_level(budget: str) -> str:
    """Normalize a budget description to one of: 经济/适中/高端."""
    for key, level in BUDGET_MAP.items():
        if key in budget:
            return level
    return "适中"


# ── Season / Month mapping ──────────────────────────────

SEASON_MONTHS = {
    "春季": {3, 4, 5},
    "夏季": {6, 7, 8},
    "秋季": {9, 10, 11},
    "冬季": {12, 1, 2},
}

MONTH_NAMES = {
    1: "一月", 2: "二月", 3: "三月", 4: "四月",
    5: "五月", 6: "六月", 7: "七月", 8: "八月",
    9: "九月", 10: "十月", 11: "十一月", 12: "十二月",
}

# ── Budget per day (price_enricher) ──────────────────────

# 按用户预算等级映射每天人均花费上限（元）
BUDGET_PER_DAY = {"经济": 300, "适中": 800, "舒适": 1500, "高端": 3000, "奢华": 5000}


__all__ = [
    "BUDGET_MAP",
    "BUDGET_LEVELS",
    "BUDGET_PER_DAY",
    "MONTH_NAMES",
    "SEASON_MONTHS",
    "normalize_budget_level",
]
