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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wb import close_session, evaluate, navigate  # noqa: E402

SESSION = "e2e-pages"
BASE = "http://localhost:5173"
RESULTS = []

PAGE_CHECKS = [
    ("/", "首页", "text.includes('TravelMind') && text.includes('智能推荐') && text.includes('图片识别')"),
    ("/recommend", "推荐页", "!!document.querySelector('input[type=text]') && text.includes('智能推荐')"),
    ("/itinerary", "行程页(fixture 预览)", "text.includes('预算分配') && text.includes('行前清单') && text.includes('实用提示') && text.includes('示例数据预览')"),
    ("/image", "图片页", "text.includes('图片识别') && text.includes('拖拽图片到这里')"),
    ("/chat", "对话式规划页", "text.includes('意图') && text.includes('目的地') && text.includes('对话式规划')"),
]


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
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
