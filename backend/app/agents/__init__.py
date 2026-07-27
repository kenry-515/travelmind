"""
TravelMind Agent — Multi-Agent Pipeline

Multi-agent travel planning system:
  - Orchestrator: 6-step pipeline coordinating all agents
  - Profile Agent: NL → structured user profile extraction
  - Trend Agent: trending places analysis (Phase 3 Day 7)
  - Recommendation Agent: 6-factor weighted scoring (Phase 3 Day 7)
  - Planning Agent: LLM itinerary generation (Phase 3 Day 7)
  - Vision Agent: travel photo analysis → taxonomy tags (Phase 5 Day 10)

顶层导出全部惰性加载（PEP 562）：import app.agents.xxx 时不会连带拉起
orchestrator / RAG / chromadb 等重依赖，加快启动也让纯逻辑模块可独立测试。
"""

from typing import Any

_LAZY_EXPORTS = {
    "TravelState": ("app.agents.orchestrator", "TravelState"),
    "run_travel_workflow": ("app.agents.orchestrator", "run_travel_workflow"),
    "extract_profile": ("app.agents.profile_agent", "extract_profile"),
    "analyze_travel_image": ("app.agents.vision_agent", "analyze_travel_image"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(target[0])
    return getattr(module, target[1])
