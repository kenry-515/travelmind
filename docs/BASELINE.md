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

## Phase 2 质量评测基线（2026-07-21 首次全量）

评测命令：`cd backend && python -X utf8 -m evals.run_evals`（12 query × 9 约束，
真实管线生成 + 确定性打分，结果见 `backend/evals/results/2026-07-21.json`）

| 指标 | 基线值 | 说明 |
|---|---|---|
| **Micro** | **75.0%** | 约束单元格 81/108 |
| **Macro** | **0.0%** | 12 条 query 无一条全约束通过 |
| **Final Pass Rate** | **0.0%** | 同 Macro |
| schema_valid | 92% | q05 西安生成失败（重试耗尽） |
| days_correct | 92% | 同上 |
| stats_place_count | 92% | 同上 |
| budget_consistent | 92% | 同上 |
| month_consistent | 92% | 同上 |
| weather_coverage | 92% | 同上 |
| route_ok | 75% | 3 条检出折返并优化 |
| **poi_verified** | **25%** | 主要短板①：高德名称索引命中弱（上海/北京公园类尤甚），改进空间大 |
| **weather_fit** | **25%** | 主要短板②：7 月雷暴季模型仍排户外，prompt 天气约束需强化 |

解读：92% 的工程约束（契约/统计/月份/预算）已稳；失分集中在两个
"真实世界"维度——POI 可核实率与天气自适应。这正是看板要量化的差距，
也是后续优化的优先方向（更名的 POI 名称归一 / 更强的天气约束注入）。

## 定时巡检现状

- 每小时 :23 全栈冒烟（cron `849cb3b1`）
- 每天 08:41 契约回归 + 页面 E2E（cron `a9f16bb9`）

## 文档漂移修正记录（Phase 0 完成项）

- `HANDOFF_TO_KIMICODE.md`：Qwen-VL→Kimi k2.6、445→896/15 城、56→84 条趋势、
  9→13 条路由、百度残留说明归档化；头部加归档说明
- `CLAUDE_CODE_START.md`（PDR）：3 处 Qwen Embedding/API 选型标注为最终实现；头部加"以最终实现为准"说明
- `README.md`：本为最小版，无漂移
- 验证：三份文档 grep `Qwen|445|56 条趋势` 零命中
