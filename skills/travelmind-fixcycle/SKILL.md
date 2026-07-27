---
name: travelmind-fixcycle
description: |
  TravelMind Agent 一站式开发循环：pytest → build → oxlint → 重启后端 → 增量评测 → 文档更新。
  当用户说"提交前检查 / 全量验证 / 跑开发循环 / fixcycle / 改完代码验收"，或修改了
  backend/app 下任何代码需要验证零劣化时使用本技能。
  将原本 6-8 步手工操作压缩为一条命令，token 消耗降低 70%+。评测自动检测增量范围，
  文档更新模板化消除手写数字误差。
  原则：脚本能跑的绝不调模型。
---

# TravelMind 一站式开发循环

## 一键命令

```bash
cd backend && bash scripts/fixcycle.sh
```

行为：pytest → build → oxlint → 重启后端 → eval_smart（增量评测）→ update_docs（文档更新）。
任一阶段失败即非零退出。

## 变体

```bash
cd backend && bash scripts/fixcycle.sh --skip-eval   # 跳过评测（快速迭代）
cd backend && bash scripts/fixcycle.sh --quick        # 仅 pytest+build+lint（最快，无评测无重启）
cd backend && bash scripts/fixcycle.sh --no-restart   # 不重启后端（已手动重启时）
```

## 组件说明

| 步骤 | 脚本 | 成本 |
|------|------|------|
| pytest | `python -m pytest -q` | 零 LLM |
| build | `npm run build` | 零 LLM |
| oxlint | `npx oxlint` | 零 LLM |
| 重启后端 | `scripts/backend_restart.sh` | 零 LLM |
| 增量评测 | `scripts/eval_smart.py` | DeepSeek token（仅受影响的 queries） |
| 文档更新 | `scripts/update_docs.py` | 零 LLM（模板化） |

## eval_smart.py — 增量评测

自动从 `git diff` 推断受影响的约束和 query 分类，只重跑必要的子集。
如果检测不到 git 变更或影响范围过大，自动回退到全量评测。

```bash
cd backend && python -X utf8 scripts/eval_smart.py                    # 自动检测改动
cd backend && python -X utf8 scripts/eval_smart.py --full              # 强制全量
cd backend && python -X utf8 scripts/eval_smart.py --report-only       # 仅对比报告
```

## update_docs.py — 文档自动更新

从评测结果 JSON 自动更新 `docs/BASELINE.md` 和 `HANDOFF_TO_KIMICODE.md`。

```bash
cd backend && python -X utf8 scripts/update_docs.py <结果.json> --phase 12.28a
cd backend && python -X utf8 scripts/update_docs.py --test-count 349   # 仅更新测试数
```

## 开发循环标准流程

```
改代码 → fixcycle.sh → 看 eval 报告 → git commit
```

**注意**：fixcycle.sh 跑完后仍需手动 `git add` + `git commit`。
如果 eval_smart 报告劣化，先修回退再提交。

## 相关技能

- `travelmind-devcycle`：仅重启后端 + 提交前验证
- `travelmind-eval`：全量评测 + 基线对比（更多分析选项）
- `travelmind-test`：冒烟 + E2E + 对话剧本
