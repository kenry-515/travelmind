---
name: travelmind-eval
description: |
  TravelMind Agent 质量评测工作流：执行 63 query × 24 约束评测并与历史基线对比。
  当用户说"跑评测 / 验证指标 / 对比基线 / Macro 有没有回退"，或改了 prompt/打分/检索/数据后验收时使用本技能。
  原则：评测执行器与对比器都是现成脚本——对比分析零 LLM 成本；只有评测执行消耗 DeepSeek token。
  🔴 铁律：评测结果文件绝不覆盖历史，必须用新文件名（YYYY-MM-DD-phaseXX_XX-vN.json）。
  💡 日常开发迭代推荐先用 **eval_smart.py**（增量评测，见 travelmind-fixcycle），出基线时再用本技能跑全量。
---

# TravelMind 评测与基线对比

## 前置条件

后端必须在线且是新代码：`cd backend && bash scripts/backend_restart.sh`（见 travelmind-devcycle）。

## 1. 快速迭代（改 prompt/打分逻辑时）

```bash
cd backend && python -X utf8 -m evals.run_evals --category standard --out evals/results/<新文件名>.json
```

30 条 standard 查询（覆盖 weather_fit 主战场），约 10-20 分钟。
**注意：参数是 `--category`，不是 `--tags`。**

## 2. 全量验收（存档基线时）

```bash
cd backend && python -X utf8 -m evals.run_evals --out evals/results/YYYY-MM-DD-phaseXX_XX-vN.json
```

63 query × 24 约束，约 25-45 分钟（DeepSeek 偶发超时重试属正常）。
文件名规则：`YYYY-MM-DD-phaseXX_XX-vN.json`，**绝不覆盖历史结果**。

## 3. 与基线对比（零 LLM 成本）

```bash
cd backend && python -X utf8 scripts/eval_compare.py <基线.json> <新跑.json>
```

输出：三级指标 delta（Micro/Macro/Final）、逐项约束变化、逐 query PASS↔fail 翻转清单、按分类通过率。

## 判定参考（Phase 12.27 基线）

- Macro ≥ 100% 为不回退（63/63 满分）；weather_fit ≥ 100%；poi_verified ≥ 100%（40/40）
- LLM 非确定性：单 query 翻转 ±2-3 条属正常波动，chat/multi-city 分类 ±20pp，必要时重跑取均值
- q08 桂林（用户明确户外摄影需求）目前已通过（Phase 12.21+ KB 室内清单补全），满分基线无合理失败

## 收尾

指标改善后更新 `docs/BASELINE.md`（新 Phase 段落，格式沿用现有），对比输出直接引用即可，不要凭记忆写数字。
