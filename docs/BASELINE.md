# BASELINE — 优化前绿色基线（Phase 0）

> 建立日期：2026-07-21
> 基线提交：`d2cb5d2`（chore: scheduled monitoring + test infra hardening）
> 用途：作为 `docs/KIMI_CODE_GOAL_PROMPT.md` 后续所有 Phase 的对照基线；
> 每个 Phase 验收时本文件的指标不得劣化（除有意的指标提升）。

## 系统事实（与代码一致）

| 项 | 值 |
|---|---|
| 知识库 | 896 景点 / 15 城市（`backend/data/attractions.json`） |
| 趋势数据 | 84 条（`backend/data/trends.json`） |
| 标签体系 | 51 个 / 6 大类（`backend/data/tags.json`） |
| 向量库 | Chroma 896 文档，1075 维（TF-IDF 70% + Tag One-Hot 30%） |
| 主 LLM | DeepSeek `deepseek-v4-flash`（非思考模式） |
| 视觉模型 | Kimi `kimi-k2.6`（`api.moonshot.cn`，按量计费） |
| API 路由 | 13 条（`/api/v1/*`） |
| 行程契约 | `docs/itinerary.schema.json` v1.0 |

## Phase 0 基线运行结果

### 契约回归（`backend/scripts/contract_regression.py`）

| 输入 | 结果 | 耗时 | 备注 |
|---|---|---|---|
| 重庆3日游，喜欢夜景和美食，带父母 | **7/7 通过** | ~28s | 标题「夏日山城 · 家庭慢游三日」，stats=实际=11 |
| 上海3日游，喜欢历史和艺术，情侣 | **7/7 通过** | ~41s | 标题「盛夏沪上 · 三日情侣漫游」，stats=实际=15 |

覆盖断言：schema 全量校验 / day 连续 / stats 地点数=实统计 /
percent 和=100 / budget 加总≈人均预算 / 月份一致 / daysCount 一致。

### 全栈冒烟（`backend/scripts/smoke_test.py`，零 LLM 成本）

| 项 | 结果 |
|---|---|
| health / weather/cities(15) / weather/三亚 / recommend/quick(天涯海角 top1) | **5/5 通过**（~26s） |

### 页面 E2E（`backend/scripts/e2e_pages.py`，零 LLM 成本）

| 项 | 结果 |
|---|---|
| 首页 / 推荐 / 行程(fixture) / 图片 / 对话式规划 | **5/5 通过**（最近一次运行） |

## 定时巡检现状

- 每小时 :23 全栈冒烟（cron `849cb3b1`）
- 每天 08:41 契约回归 + 页面 E2E（cron `a9f16bb9`）

## 文档漂移修正记录（Phase 0 完成项）

- `HANDOFF_TO_KIMICODE.md`：Qwen-VL→Kimi k2.6、445→896/15 城、56→84 条趋势、
  9→13 条路由、百度残留说明归档化；头部加归档说明
- `CLAUDE_CODE_START.md`（PDR）：3 处 Qwen Embedding/API 选型标注为最终实现；头部加"以最终实现为准"说明
- `README.md`：本为最小版，无漂移
- 验证：三份文档 grep `Qwen|445|56 条趋势` 零命中
