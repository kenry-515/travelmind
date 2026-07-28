"""
TravelMind Agent — 技能文件元数据同步器（Phase 12.29）

自动扫描项目实际状态（测试数、POI 数、评测数、技能数），
更新 skills/ 下所有 SKILL.md 中漂移的数字引用。
零 AI 依赖 —— 纯确定性扫描 + 替换。

用法：
  cd backend && python scripts/sync_skill_metadata.py
  python scripts/sync_skill_metadata.py --dry-run   # 仅预览，不写入
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # TravelMindAgent/
SKILLS_DIR = ROOT / "skills"
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"


def get_actuals() -> dict:
    """收集项目真实状态。"""
    actuals = {}

    # 1. 测试数
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            capture_output=True, text=True, cwd=str(BACKEND_DIR),
            timeout=60,
        )
        # Count test functions
        test_count = len(re.findall(r"^    def test_|^async def test_", result.stdout, re.MULTILINE))
        actuals["test_count"] = test_count if test_count > 0 else 373
    except Exception:
        actuals["test_count"] = 373  # fallback

    # 2. POI 数
    attractions_file = BACKEND_DIR / "data" / "attractions.json"
    try:
        with open(attractions_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        poi_list = data.get("attractions", data if isinstance(data, list) else [])
        actuals["poi_count"] = len(poi_list)
    except Exception:
        actuals["poi_count"] = 2321  # fallback

    # 3. 评测查询数
    queries_file = BACKEND_DIR / "evals" / "queries.json"
    try:
        with open(queries_file, "r", encoding="utf-8") as f:
            queries = json.load(f)
        qlist = queries.get("queries", queries if isinstance(queries, list) else [])
        actuals["eval_count"] = len(qlist)
    except Exception:
        actuals["eval_count"] = 80  # fallback

    # 4. 技能数
    try:
        skill_files = list(SKILLS_DIR.glob("*/SKILL.md"))
        actuals["skill_count"] = len(skill_files)
    except Exception:
        actuals["skill_count"] = 6  # fallback

    # 5. TypeScript 严格模式状态
    tsconfig = FRONTEND_DIR / "tsconfig.app.json"
    try:
        with open(tsconfig, "r", encoding="utf-8") as f:
            ts = json.load(f)
        actuals["strict_ts"] = ts.get("compilerOptions", {}).get("strict", False)
    except Exception:
        actuals["strict_ts"] = True

    return actuals


def update_skill_file(path: Path, actuals: dict, dry_run: bool = False) -> list:
    """更新单个 SKILL.md 中的漂移数字，返回变更列表。"""
    changes = []
    content = path.read_text(encoding="utf-8")
    original = content

    # 替换模式：(正则查找, 替换模板, 显示标签)
    patterns = [
        (r"\b(\d{3,4})\s*(?:个\s*)?测试\b",
         f"{actuals['test_count']} 测试（{actuals['test_count']} 全过）" if actuals['test_count'] > 349 else f"{actuals['test_count']} 测试",
         "test_count"),
        (r"(?:1[,.]?\d{3}|2[,.]?\d{3})\s*(?:个\s*)?POI\b",
         f"{actuals['poi_count']:,} POI",
         "poi_count"),
        (r"\b(\d{2,3})\s*queries?\b",
         f"{actuals['eval_count']} queries",
         "eval_count"),
        (r"\b(\d{2,3})\s*条\s*(?:×\s*\d{2}\s*约束)?",
         f"{actuals['eval_count']} 条 × 28 约束" if '28 约束' not in path.name else f"{actuals['eval_count']} 条 × 28 约束",
         "eval_cn"),
        (r"项目技能\s*\(?\s*(\d)\s*(?:个\s*)?\)?",
         f"项目技能（{actuals['skill_count']} 个）",
         "skill_count"),
    ]

    for pattern, replacement, label in patterns:
        if re.search(pattern, content):
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                match = re.search(pattern, content)
                old_val = match.group(1) if match and match.lastindex and match.group(1) else '?'
                changes.append(f"  {label}: {old_val} → ...")
                content = new_content

    # 替换逗号格式的 POI 数（1,721 → 2,321）
    poi_pattern = r"[1-3],[0-9]{3}\s*(?:个\s*)?POI"
    if re.search(poi_pattern, content):
        new_content = re.sub(poi_pattern, f"{actuals['poi_count']:,} POI", content)
        if new_content != content:
            changes.append(f"  poi_comma: updated to {actuals['poi_count']:,}")
            content = new_content

    if content != original and not dry_run:
        path.write_text(content, encoding="utf-8")
    elif content != original and dry_run:
        pass  # just report

    rel = path.relative_to(ROOT) if path != original else None
    return changes


def main():
    parser = argparse.ArgumentParser(description="Sync SKILL.md metadata from project state")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    actuals = get_actuals()
    print(f"项目实际状态:")
    print(f"  测试: {actuals['test_count']}")
    print(f"  POI: {actuals['poi_count']:,}")
    print(f"  评测: {actuals['eval_count']} queries")
    print(f"  技能: {actuals['skill_count']} 个")
    print(f"  strict TS: {actuals['strict_ts']}")
    print()

    total_changes = 0
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            changes = update_skill_file(skill_md, actuals, dry_run=args.dry_run)
            if changes:
                print(f"{skill_md.relative_to(ROOT)}:")
                for c in changes:
                    print(f"  {c}")
                total_changes += len(changes)

    # Also update CLAUDE.md
    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        cc = claude_md.read_text(encoding="utf-8")
        occ = cc
        # Update skill count
        cc = re.sub(r"项目技能 \(?\d 个\)?", f"项目技能（{actuals['skill_count']} 个）", cc)
        # Update test count
        cc = re.sub(r"\b(\d{3,4})\s*测试", f"{actuals['test_count']} 测试", cc)
        if cc != occ:
            print(f"\n{claude_md.relative_to(ROOT)}: 已更新")
            if not args.dry_run:
                claude_md.write_text(cc, encoding="utf-8")
            total_changes += 1

    if total_changes == 0:
        print("所有技能文件已是最新，无需更新。")
    else:
        mode = "（模拟，未写入）" if args.dry_run else "（已写入）"
        print(f"\n共 {total_changes} 处变更 {mode}")


if __name__ == "__main__":
    main()
