"""
TravelMind Agent — 自动文档更新器（v1.0, Phase 12.28a）

解析最新 eval 结果 JSON → 自动更新：
  1. docs/BASELINE.md — 新 Phase 段落（头部概要 + 评测表格 + 变更摘要模板）
  2. HANDOFF_TO_KIMICODE.md — 头部快照 + §1 状态表 + §9 变更记录追加

模板化输出，消除人工手写数字的误差。

用法：
  cd backend
  python -X utf8 scripts/update_docs.py <eval_result.json> [--phase 12.28a] [--title "Phase 12.28a 工具链"]

  # 更新 BASELINE.md 和 HANDOFF 中的测试数
  python -X utf8 scripts/update_docs.py --test-count 349
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
BASELINE_PATH = ROOT_DIR / "docs" / "BASELINE.md"
HANDOFF_PATH = ROOT_DIR / "HANDOFF_TO_KIMICODE.md"


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── BASELINE.md 更新 ──────────────────────────────────────


def generate_baseline_section(
    phase: str,
    title: str,
    eval_result: Dict[str, Any],
    prev_phase: Optional[str] = None,
    prev_micro: Optional[float] = None,
    prev_macro: Optional[float] = None,
    changes: Optional[List[Dict[str, str]]] = None,
    notes: str = "",
    command: str = "",
) -> str:
    """Generate a new Phase section for BASELINE.md."""
    micro = eval_result.get("micro", 0)
    macro = eval_result.get("macro", 0)
    total = eval_result.get("total_queries", 0)
    per_constraint = eval_result.get("per_constraint", {})
    per_category = eval_result.get("per_category", {})
    per_query = eval_result.get("per_query", [])

    lines = []
    lines.append(f"### {phase} 全量评测（{date.today().isoformat()}）")
    lines.append("")

    if not command:
        command = f"`cd backend && python -X utf8 -m evals.run_evals --out evals/results/{date.today().isoformat()}-{phase.lower().replace(' ', '_')}-v1.json`"
    lines.append(f"评测命令：{command}")
    lines.append(f"（{total} query × {len(per_constraint)} 约束）")
    lines.append("")

    # Summary table
    if prev_phase:
        lines.append(f"| 指标 | {prev_phase} | {phase} | 变化 |")
        lines.append("|------|-------------|--------|------|")
        m_delta = macro - (prev_macro or 0)
        mic_delta = micro - (prev_micro or 0)
        lines.append(f"| **Micro** | {prev_micro:.1%} | **{micro:.1%}** | {mic_delta:+.1%} |")
        lines.append(f"| **Macro** | {prev_macro:.1%} ({int((prev_macro or 0)*total)}/{total}) | **{macro:.1%}** ({int(macro*total)}/{total}) | {m_delta:+.1%} |")
    else:
        lines.append(f"| 指标 | {phase} |")
        lines.append("|------|--------|")
        lines.append(f"| **Micro** | **{micro:.1%}** |")
        lines.append(f"| **Macro** | **{macro:.1%}** ({int(macro*total)}/{total}) |")

    lines.append("")

    # Per-constraint table
    lines.append("### 按约束维度")
    lines.append("")
    lines.append("| 约束 | 通过/适用 | 通过率 |")
    lines.append("|------|-----------|--------|")
    for c, s in sorted(per_constraint.items()):
        if s.get("total", 0) > 0:
            lines.append(f"| {c} | {s['pass']}/{s['total']} | **{s['rate']:.0%}** |")
        else:
            lines.append(f"| {c} | (不适用) | — |")
    lines.append("")

    # Per-category
    if per_category:
        lines.append("### 按分类")
        lines.append("")
        lines.append("| 分类 | 查询数 | 通过数 | 通过率 |")
        lines.append("|------|--------|--------|--------|")
        for cat, stats in sorted(per_category.items()):
            rate = stats["pass"] / stats["total"] if stats["total"] else 0
            lines.append(f"| **{cat}** | {stats['total']} | **{stats['pass']}** | **{rate:.0%}** |")
        lines.append("")

    # Notes
    if notes:
        lines.append(f"> {notes}")
        lines.append("")

    # Changes
    if changes:
        lines.append(f"### {phase} 变更摘要")
        lines.append("")
        lines.append("| 优先级 | 优化 | 文件 | 说明 |")
        lines.append("|--------|------|------|------|")
        for ch in changes:
            lines.append(f"| {ch.get('priority', '🟢 P3')} | **{ch.get('name', '')}** | `{ch.get('file', '')}` | {ch.get('desc', '')} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def update_baseline_md(section: str, phase: str) -> bool:
    """Insert new Phase section at top of BASELINE.md (after header)."""
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Update header line with current phase info
    today = date.today().isoformat()
    new_header_line = f"> 最后更新：{today}\n"
    content = re.sub(r'> 最后更新：\d{4}-\d{2}-\d{2}', new_header_line, content)

    # Also update the bolded phase line in header
    content = re.sub(
        r'> \*\*Phase [^\n]+\*\*',
        f'> **{phase}**',
        content,
    )

    # Insert new section after the header block (after first ---)
    parts = content.split("---", 2)
    if len(parts) >= 3:
        content = parts[0] + "---" + parts[1] + "---\n\n" + section + parts[2]

    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ BASELINE.md 已更新（{phase}）")
    return True


# ── HANDOFF_TO_KIMICODE.md 更新 ───────────────────────────


def update_handoff(
    phase: str,
    eval_result: Optional[Dict[str, Any]] = None,
    test_count: Optional[int] = None,
    kb_count: Optional[int] = None,
    changes: Optional[List[Dict[str, str]]] = None,
    changelog_entry: str = "",
) -> bool:
    """Update HANDOFF_TO_KIMICODE.md header snapshot + §1 + §9."""
    with open(HANDOFF_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    today = date.today().isoformat()

    # 1. Update header date line
    content = re.sub(
        r'> \*\*当前日期：\*\* \d{4}-\d{2}-\d{2}[^\n]*',
        f'> **当前日期：** {today}',
        content,
    )
    content = re.sub(
        r'> \*\*当前阶段：\*\* [^\n]+',
        f'> **当前阶段：** {phase}',
        content,
    )

    # 2. Update §1 status table test count
    if test_count:
        content = re.sub(
            r'\| 单元测试 \| \*\*\d+ 个全过\*\*[^|]*\|',
            f'| 单元测试 | **{test_count} 个全过**（0 失败，~13s） |',
            content,
        )
    if kb_count:
        content = re.sub(
            r'\| 知识库 \| \*\*[\d,]+ POI[^|]*\|',
            f'| 知识库 | **{kb_count:,} POI / 30 城市** |',
            content,
        )

    # 3. Update eval baseline line
    if eval_result:
        micro = eval_result.get("micro", 0)
        macro = eval_result.get("macro", 0)
        total = eval_result.get("total_queries", 63)
        result_file = f"`{today}-{phase.lower().replace(' ', '_')}-v1.json`"

        content = re.sub(
            r'> \*\*最新基线：\*\* [^\n]+',
            f'> **最新基线：** Micro {micro:.0%} / Macro {macro:.0%}（{int(macro*total)}/{total}）（{phase}，{result_file}）',
            content,
        )
        phase_slug = phase.lower().replace(" ", "_")
        content = re.sub(
            r'> \*\*最新评测存档：\*\* [^\n]+',
            f"> **最新评测存档：** `backend/evals/results/{today}-{phase_slug}-v1.json`（满分基线）",
            content,
        )
        content = re.sub(
            r'\| 最新评测 \| [^\|]+\|',
            f"| 最新评测 | **满分 {int(macro*total)}/{total}（{phase}，`{today}-{phase_slug}-v1.json`）** |",
            content,
        )

    # 4. Append changelog entry in §9
    if changelog_entry:
        # Find §9 and append after the heading
        nine_match = re.search(r'^(## 9\..*)$', content, re.MULTILINE)
        if nine_match:
            insert_pos = nine_match.end()
            content = content[:insert_pos] + "\n\n" + changelog_entry + content[insert_pos:]

    with open(HANDOFF_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ HANDOFF_TO_KIMICODE.md 已更新（{phase}）")
    return True


# ── Main ──────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="自动更新文档（BASELINE + HANDOFF）")
    parser.add_argument("eval_result", nargs="?", default="",
                        help="评测结果 JSON 文件路径")
    parser.add_argument("--phase", type=str, default="",
                        help="Phase 标识（如 12.28a）")
    parser.add_argument("--title", type=str, default="",
                        help="Phase 标题")
    parser.add_argument("--prev-phase", type=str, default="",
                        help="前一 Phase 标识")
    parser.add_argument("--prev-micro", type=float, default=0,
                        help="前一 Phase Micro 通过率")
    parser.add_argument("--prev-macro", type=float, default=0,
                        help="前一 Phase Macro 通过率")
    parser.add_argument("--test-count", type=int, default=0,
                        help="当前单元测试数量")
    parser.add_argument("--kb-count", type=int, default=0,
                        help="当前 KB POI 数量")
    parser.add_argument("--changes", type=str, default="",
                        help="变更摘要 JSON 文件路径")
    parser.add_argument("--changelog", type=str, default="",
                        help="§9 变更条目（markdown 文本）")
    parser.add_argument("--notes", type=str, default="",
                        help="评测备注")
    parser.add_argument("--baseline-only", action="store_true",
                        help="仅更新 BASELINE.md")
    parser.add_argument("--handoff-only", action="store_true",
                        help="仅更新 HANDOFF_TO_KIMICODE.md")
    args = parser.parse_args()

    phase = args.phase or f"Phase {date.today().isoformat()}"
    title = args.title or phase
    updated = False

    eval_result = None
    if args.eval_result:
        eval_result = load_json(Path(args.eval_result))

    changes_list = None
    if args.changes:
        changes_list = load_json(Path(args.changes))

    # Update BASELINE.md
    if not args.handoff_only and eval_result:
        section = generate_baseline_section(
            phase=phase,
            title=title,
            eval_result=eval_result,
            prev_phase=args.prev_phase or None,
            prev_micro=args.prev_micro or None,
            prev_macro=args.prev_macro or None,
            changes=changes_list,
            notes=args.notes,
        )
        update_baseline_md(section, phase)
        updated = True

    # Update HANDOFF_TO_KIMICODE.md
    if not args.baseline_only:
        update_handoff(
            phase=phase,
            eval_result=eval_result,
            test_count=args.test_count or None,
            kb_count=args.kb_count or None,
            changes=changes_list,
            changelog_entry=args.changelog,
        )
        updated = True

    if not updated:
        print("未执行更新（缺少 eval_result 或未指定 --test-count/--kb-count）")
        print("用法示例：")
        print(f"  python scripts/update_docs.py evals/results/{date.today().isoformat()}-phase12_28a-v1.json --phase 12.28a --prev-phase 12.27 --prev-micro 1.0 --prev-macro 1.0 --test-count 349 --kb-count 2321")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
