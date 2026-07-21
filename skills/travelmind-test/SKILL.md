---
name: travelmind-test
description: |
  TravelMind Agent 的固定化测试工作流：全栈冒烟、行程契约回归、浏览器页面 E2E。
  当用户要求"跑测试 / 冒烟 / 回归 / 验证系统"或提交前检查时使用本技能。
  原则（来自 CLI+Skill 模式）：脚本能跑的绝不调模型——冒烟与 E2E 零 LLM 成本；
  只有契约回归消耗少量 DeepSeek/Kimi token。
---

# TravelMind Test Workflows

三个固定化流程，全部有脚本，直接跑，不要手写临时验证代码。

## 前置条件

- 后端：`cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 前端（仅 E2E 需要）：`cd frontend && npm run dev`
- 浏览器 E2E 需要 Kimi WebBridge daemon 运行中（`kimi-webbridge status`）

## 1. 全栈冒烟（零 LLM 成本）

```bash
cd backend && python -X utf8 scripts/smoke_test.py
```

断言：health(api=healthy) → weather/cities(15 城) → weather/三亚 →
recommend/quick（纯 RAG+打分，无 LLM，0 token）→（可选）--with-vision 图片识别。
任何一项失败 → 非零退出码 + 失败项明细。

## 2. 行程契约回归（消耗少量 DeepSeek token）

```bash
cd backend && python -X utf8 scripts/contract_regression.py
```

固定输入「重庆3日游，喜欢夜景和美食，带父母」真实生成，然后断言：
schema 全量校验 / day 连续 / stats 地点数=实统计 / percent 和=100 /
budget 加总≈人均预算(≤15%) / 月份一致 / 非游览停靠排除。

## 3. 浏览器页面 E2E（零 LLM 成本）

```bash
cd backend && python -X utf8 scripts/e2e_pages.py
```

通过 WebBridge daemon 打开 5 个页面断言关键元素：首页(4 入口) /
推荐页(搜索框) / 行程页(fixture 预览 5 区块) / 图片页(上传区) /
对话页(意图状态条)。WebBridge 调用一律走 `scripts/wb.py` 封装
（临时 JSON 文件 + curl.exe，禁止 shell 内联中文）。

## 4. 质量评测看板（每周/按需，有 LLM 成本）

```bash
cd backend && python -X utf8 -m evals.run_evals [--limit N]
```

对 `backend/evals/queries.json`（12 条，可扩充）逐条真实生成，
再用确定性打分器输出 **Micro / Macro / Final Pass Rate** 三级指标，
结果落盘 `backend/evals/results/YYYY-MM-DD.json`。
指标含义与当前基线见 `docs/BASELINE.md` 和 README「质量评测」。
不并入每小时冒烟（有成本）；需要提升通过率时逐项看 `per_constraint`。

## 定时巡检（cron）

- **每小时 :23**：`smoke_test.py`（零 LLM 成本），失败时自动重启后端重试一次再上报
- **每天 08:41**：`contract_regression.py`（少量 DeepSeek token）+ 前端在线时附带 `e2e_pages.py`
- 前端 dev server 不在线时 `e2e_pages.py` 自动跳过（退出码 0，不误报）
- 修改/取消：让用户直接说（如"把每小时冒烟改成每两小时"）

## 失败排查

- 冒烟 health 失败 → 后端没起或端口被占（`netstat -ano | findstr :8000`）
- recommend/quick 失败 → Chroma 向量库未初始化（跑 `scripts/build_knowledge_base.py`）
- 契约回归连续失败 → 看 backend 日志 Planning attempt 的具体校验错误
- E2E 连接拒绝 → `kimi-webbridge.exe start`，并确认浏览器扩展已连接
