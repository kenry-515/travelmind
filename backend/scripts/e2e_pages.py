"""
TravelMind Agent — 页面 E2E（零 LLM 成本）

通过 WebBridge daemon 打开 5 个页面，断言关键元素渲染。
前置：前端 dev server (:5173) + WebBridge daemon + 浏览器扩展已连接。

用法:
    cd backend
    python scripts/e2e_pages.py
"""

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wb import close_session, evaluate, navigate  # noqa: E402

SESSION = "e2e-pages"
BASE = "http://localhost:5173"
RESULTS = []

PAGE_CHECKS = [
    ("/", "首页", "text.includes('TravelMind') && text.includes('智能推荐') && text.includes('图片识别')"),
    ("/recommend", "推荐页", "!!document.querySelector('input[type=text]') && text.includes('智能推荐')"),
    ("/itinerary", "行程页(空状态)", "text.includes('尚未生成行程') && text.includes('对话规划')"),
    ("/image", "图片页", "text.includes('图片识别') && text.includes('拖拽图片到这里')"),
    ("/chat", "对话式规划页", "text.includes('意图') && text.includes('目的地') && text.includes('对话式规划')"),
]


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    # 前端不在不算失败（定时巡检场景下前端 dev server 不一定常开）
    try:
        httpx.get(BASE, timeout=3, trust_env=False)
    except Exception:
        print(f"⏭️  前端 {BASE} 不可达 — 跳过页面 E2E（dev server 未启动）")
        return 0

    try:
        navigate(BASE + "/", SESSION, new_tab=True, group_title="E2E 页面巡检")
    except RuntimeError as e:
        print(f"WebBridge 不可用: {e}")
        return 1

    for path, name, expr in PAGE_CHECKS:
        try:
            navigate(BASE + path, SESSION)
            time.sleep(2.5)
            value = evaluate(
                f"(() => {{ const text = document.body.innerText || ''; return JSON.stringify({{ pass: {expr}, head: text.slice(0, 80) }}); }})()",
                SESSION,
            )
            result = json.loads(value) if isinstance(value, str) else value
            check(name, bool(result.get("pass")), result.get("head", "")[:50])
        except Exception as e:
            check(name, False, str(e)[:120])

    try:
        close_session(SESSION)
    except Exception:
        pass

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n===== 页面 E2E: {passed}/{len(RESULTS)} 通过 =====")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
