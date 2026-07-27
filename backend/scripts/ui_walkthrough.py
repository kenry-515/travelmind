"""
TravelMind Agent — UI 截图走查脚本（WebBridge）

一键产出全站走查截图：
  - 桌面 6 页：/ /chat /recommend /itinerary /image /history
  - 移动 3 页：iframe 390px 模拟视口（WebBridge 不支持真视口切换的替代方案）

单页失败不阻断（打印失败继续下一页）；会话自动清理。
前置：vite dev (:5173) + WebBridge daemon + 浏览器扩展已连接。

用法：
  cd backend
  python scripts/ui_walkthrough.py                 # 全部 9 张
  python scripts/ui_walkthrough.py --only desktop  # 只桌面
  python scripts/ui_walkthrough.py --only mobile   # 只移动
输出：docs/images/walkthrough/desktop_{name}.jpeg / mobile_{name}.jpeg
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wb import call, close_session, navigate  # noqa: E402

SESSION = "ui-walkthrough"
BASE = "http://localhost:5173"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "images" / "walkthrough"

DESKTOP_PAGES = [
    ("/", "home"),
    ("/chat", "chat"),
    ("/recommend", "recommend"),
    ("/itinerary", "itinerary"),
    ("/image", "image"),
    ("/history", "history"),
]
MOBILE_PAGES = [("/", "home"), ("/chat", "chat"), ("/recommend", "recommend")]

_MOBILE_IFRAME_JS = """(() => {
  document.body.innerHTML='';
  const f=document.createElement('iframe');
  f.src='%s';
  f.style.cssText='position:fixed;top:0;left:0;width:390px;height:780px;z-index:99999;border:0;background:white';
  document.body.appendChild(f);
  return 'ok'
})()"""


def _shot(path: str, name: str, out: Path) -> bool:
    r = call("screenshot", {
        "format": "jpeg", "quality": 72,
        "path": str(out),
        **({"selector": "iframe"} if "mobile" in out.stem else {}),
    }, session=SESSION, timeout=90)
    size = r.get("sizeBytes") if isinstance(r, dict) else 0
    print(f"  {'✅' if size else '❌'} {name} → {out.name} ({size}B)")
    return bool(size)


def main() -> None:
    parser = argparse.ArgumentParser(description="UI 截图走查")
    parser.add_argument("--only", choices=["desktop", "mobile"], default="")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        close_session(SESSION)
    except Exception:
        pass
    time.sleep(1)

    ok = True
    if args.only in ("", "desktop"):
        print("== 桌面 6 页 ==")
        first = True
        for path, name in DESKTOP_PAGES:
            try:
                navigate(f"{BASE}{path}", SESSION, new_tab=first)
                first = False
                time.sleep(3)
                ok &= _shot(path, name, OUT_DIR / f"desktop_{name}.jpeg")
            except Exception as e:
                print(f"  ❌ {name}: {str(e)[:80]}")
                ok = False
                time.sleep(2)

    if args.only in ("", "mobile"):
        print("== 移动 3 页（iframe 390px）==")
        try:
            navigate(f"{BASE}/", SESSION, new_tab=False)
            time.sleep(2)
        except Exception as e:
            print(f"  ❌ 容器页加载失败: {str(e)[:80]}")
            ok = False
        for path, name in MOBILE_PAGES:
            try:
                from wb import evaluate
                evaluate(_MOBILE_IFRAME_JS % f"{BASE}{path}", SESSION)
                time.sleep(4.5)
                ok &= _shot(path, name, OUT_DIR / f"mobile_{name}.jpeg")
            except Exception as e:
                print(f"  ❌ mobile {name}: {str(e)[:80]}")
                ok = False
                time.sleep(2)

    print(f"\n输出目录: {OUT_DIR}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
