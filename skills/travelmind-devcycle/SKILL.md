---
name: travelmind-devcycle
description: |
  TravelMind Agent 后端开发循环：重启后端（可选重建 Chroma）、等待就绪、提交前全量验证。
  当用户说"重启后端 / 重建向量库 / 提交前检查 / 全量验证"，或改了后端代码需要重新部署时使用本技能。
  原则：脚本能跑的绝不调模型——重启与验证全部零 LLM 成本。
  💡 推荐优先使用 **travelmind-fixcycle** 技能（一键全流程），本技能用于需要手动控制重启或验证步骤的场景。
---

# TravelMind 后端开发循环

全部有脚本，直接跑，不要手写 PowerShell/进程管理临时代码。

## 1. 重启后端（改了代码之后必做）

```bash
cd backend && bash scripts/backend_restart.sh
```

行为：杀掉 :8000 的 uvicorn → 后台启动 → 轮询健康检查 → 打印 `READY`。
**uvicorn 不带 --reload，改了 backend/app 下任何代码都必须重启，否则跑的是旧代码。**

带 Chroma 重建（ attractions.json 或向量库数据变了时）：

```bash
cd backend && bash scripts/backend_restart.sh --rebuild
```

等价于 `build_kb.py --only normalize,rebuild` + 重启。日志在 `/tmp/travelmind-backend.log`。

## 2. 提交前全量验证（零 LLM 成本）

```bash
cd backend && bash scripts/full_verify.sh
```

四步断言链，任一失败即非零退出：
1. `python -m pytest`（当前基线 349 全过）
2. `npm run build`（TypeScript 0 错误）
3. `npx oxlint`（0 错误）
4. `scripts/smoke_test.py`（需后端在线，不在线则 SKIP 并提示）

## 3. 快速评测冒烟（少量 DeepSeek token）

```bash
cd backend && python -X utf8 -m evals.run_evals --limit 5
```

全量/分类评测与基线对比用 **travelmind-eval** 技能，不要在本技能里跑全量。
