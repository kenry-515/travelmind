# Kimi Code /goal 模式提示词：TravelMind Agent 优化计划

> 用法：本文件是给 Kimi Code `/goal` 模式使用的目标说明书。
> **推荐逐阶段执行**：每轮对话用 `/goal` 投喂「通用约束 + 某一个 Phase」即可，验收通过后再进行下一个 Phase。
> 也可以一次性投喂全文，让 Kimi Code 按依赖顺序自行推进。
> 撰写日期：2026-07-21。项目根目录：`D:\TravelMindAgent`

---

## 第一部分：项目背景（必读上下文）

TravelMind Agent（智游伴）是一个 AI 旅行规划智能体：**多 Agent 协作 + RAG + 多模态**，多轮对话收敛意图，一键生成经过真实数据校验的结构化行程卡片。

### 技术栈与架构

```
L1 交互层   React 19 + Vite + TypeScript + Tailwind（frontend/，端口 5173，/api 代理到 8000）
L2 意图层   FastAPI + 对话状态机（槽位收敛、修改分流、局部重生成）
L3 生成层   LangGraph 七节点管线（Profile→Trend→Weather→RAG→Recommend→Plan）
            + JSON Schema 契约校验 + 高德 POI 存续/顺路校验
```

- 后端：`backend/app/`，Python 3.11+，FastAPI，端口 8000，统一前缀 `/api/v1`
- LLM：DeepSeek（主）、Kimi 开放平台（视觉识别，kimi-k2.6）、高德地图（POI/路线）、Open-Meteo（天气，免费）
- 向量库：Chroma（已持久化，26MB）
- 知识库：`backend/data/attractions.json`（896 景点 / 15 城市，1.3MB）+ 趋势数据 84 条
- 数据库：PostgreSQL + SQLAlchemy（`backend/app/database/models.py` 已存在但基本未用，开发期可选）

### 关键文件地图

| 文件 | 说明 |
|---|---|
| `backend/app/agents/orchestrator.py`（433 行） | LangGraph 七节点管线 |
| `backend/app/agents/dialog_manager.py`（297 行） | 对话状态机：槽位收敛→确认→生成→交付；会话存于进程内 `_sessions` 字典（TTL 2h） |
| `backend/app/services/itinerary_contract.py`（283 行） | 行程契约校验 |
| `docs/itinerary.schema.json` | 行程 JSON Schema 契约 |
| `backend/app/services/route_optimizer.py` | 高德 POI 存续校验 + 顺路处理 |
| `backend/app/services/vision_service.py` | Kimi 视觉识别 |
| `docs/itinerary.example.json` / `docs/itinerary.example.cq.json` | 契约回归基准 fixture（上海/重庆） |
| `skills/travelmind-test/` | 既有测试工作流：零成本全栈冒烟、契约回归、WebBridge E2E；已配置每小时冒烟 + 每日回归定时任务 |
| `frontend/src/` | 5 个页面：首页 / 对话 / 推荐 / 行程 / 图片识别；行程类型文件近 2000 行由 schema 生成 |

### 当前完成度

以 PDR 的 Demo 目标计约 90%；以「可用产品」计约 40–50%。核心差异化能力（真实数据校验、槽位收敛、局部重生成、契约校验）已落地，当前差距不在"智能"而在"产品化"。

### 竞品调研结论（优化的战略依据）

1. 学术与市场双重验证：**纯 LLM 规划不可靠**（TravelPlanner benchmark 中 GPT-4 全局通过率仅 0.6%），"LLM + 外部真实数据校验"是正确路线——本项目的核心资产就是校验层，必须把它**讲出来、量化出来**。
2. 用户最大痛点可量化：90% 的 AI 行程至少含一处错误、52% 推荐了营业时间外的场所、24% 推荐了已永久关闭的店、25% 路线要折返；81% 用户会逐条人工复核，主因是**价格不可信**。
3. 定位：**做"决策层"不做"交易层"**——不与 OTA 拼实时票价/库存/支付闭环（供应链壁垒），强化"可校验、可解释、可局部修改"的可信行程引擎标签。

---

## 第二部分：通用约束（每个 Phase 都适用，投喂时必须包含）

1. **不破坏既有契约**：`docs/itinerary.schema.json` 的任何变更必须向后兼容，或同步更新：两个回归 fixture、前端由 schema 生成的类型文件、`itinerary_contract.py`。
2. **回归必须全绿**：每个 Phase 完成后运行 `skills/travelmind-test` 中的契约回归（上海 + 重庆两个 fixture）和全栈冒烟，全部通过才算完成。
3. **数据不许写死在代码里**：POI/景点/趋势数据一律走 `backend/data/` 数据文件或数据库（PDR 第 87 条红线）。
4. **不引入复杂爬虫系统**（PDR 第 91 条红线）。外部数据只用公开 API。
5. **API Keys 安全**：只读 `.env`，绝不把真实 key 写进代码/测试/文档；新增配置项同步更新 `.env.example`。
6. **同步更新文档**：任何行为变更同步更新 `README.md`；新增模块在对应目录写清注释。文档中的模型名、数据规模等数字必须与实际代码一致（禁止文档漂移）。
7. **先读后改**：修改任何文件前先完整阅读该文件及相关调用方；小步提交，每个 Phase 内按任务粒度 commit，commit message 用中文说明"做了什么、为什么"。
8. **验收驱动**：每个 Phase 列出了可执行的验收命令/检查点，全部通过后才允许进入下一个 Phase；不允许"差不多就行"。
9. 遇到需求歧义或需要破坏性变更（删表、改 API 路径、换框架）时，**停下来列出方案让我选择**，不要自行决定。

---

## 第三部分：分阶段优化任务

### Phase 0：文档修正与基准确认（前置，半小时量级）

**目标**：消除文档漂移，建立优化前的绿色基线。

任务：
1. 通读 `HANDOFF_TO_KIMICODE.md`、`CLAUDE_CODE_START.md`、`README.md`，修正所有与实际代码不符的内容（已知漂移：视觉模型实为 Kimi k2.6 而非 Qwen-VL；景点数实为 896/15 城市而非 445；根目录 `data/` 为空，实际数据在 `backend/data/`）。
2. 运行一次完整契约回归 + 全栈冒烟，把结果（通过/耗时）记录到 `docs/BASELINE.md`，作为后续所有 Phase 的对照基线。

验收：
- [ ] 三份文档中不再出现 Qwen-VL、445 等过时数字
- [ ] `docs/BASELINE.md` 存在，记录了回归与冒烟的通过证据

---

### Phase 1（P0）：校验报告可视化 —— 把"真实数据校验"从后台能力变成用户可见的卖点

**背景**：高德 POI 存续校验、顺路校验、天气校验目前都在后台静默运行，用户感知不到。市场调研证明"可校验、可解释"是本项目对大厂和纯 LLM 产品的核心差异化。

任务：
1. **后端**：在行程生成结果中新增 `validation_report` 字段（先扩展 `docs/itinerary.schema.json`，向后兼容的可选字段），汇总每个行程的校验结论：
   - 每个 POI 的存续状态（在营/未核实/已关闭及来源时间戳）
   - 每日路线的顺路结论（总里程、是否折返、折返点提示）
   - 天气校验结论（逐日天气 vs 室内/室外活动匹配度）
   - 汇总级徽章数据，例如：`{"poi_verified": "12/12", "route_backtrack": false, "weather_fit": "good"}`
   - 校验逻辑复用现有 `itinerary_contract.py` 与 `route_optimizer.py`，不另起炉灶；校验失败项必须带人类可读的原因说明。
2. **前端**：在行程页渲染"校验报告卡片"：
   - 顶部徽章行（✓ 全部 POI 在营 ✓ 无折返 ✓ 天气适宜 这类直观结论）
   - 每日时间轴上把顺路/天气结论就近标注
   - 校验未通过/未核实的项用醒目但克制的样式标出，并给出原因
   - 如行程页已有地图组件，将顺路结论（路线走向、折返点）渲染到地图上；没有地图组件则本期只做卡片，不做地图。
3. 更新 `docs/itinerary.example.json` 与 `itinerary.example.cq.json` 两个 fixture，纳入新字段。

验收：
- [ ] `POST /api/v1/itinerary/generate` 返回体含 `validation_report`，通过 schema 校验
- [ ] 上海、重庆两个 fixture 的契约回归全绿
- [ ] 前端行程页可见校验报告卡片，至少覆盖：POI 存续汇总、顺路结论、天气结论
- [ ] 冒烟测试通过；`README.md` 架构说明中补充 validation_report 一句话介绍

---

### Phase 2（P0）：行程质量评测体系 —— 把校验能力量化成可回归的指标看板

**背景**：学术界用约束通过率衡量规划质量（TravelPlanner 的 Micro/Macro/Final 三级指标）。本项目已有契约回归 fixture，但缺少"质量分"。这是开源圈差异化最强的标签，也能防止后续优化劣化规划质量。

任务：
1. 新建 `backend/evals/` 目录，实现 `run_evals.py` 评测脚本：
   - 评测集：先内置 10–20 条覆盖不同城市/天数/预算/兴趣组合的中文测试 query（放在 `backend/evals/queries.json`，不许写死在脚本里）
   - 对每条 query 真实调用完整生成管线（走 LLM），然后运行**确定性打分器**：
     - **Micro 通过率**：逐项约束（schema 合规、POI 存续、无折返、预算约束满足、天数正确、天气匹配等）的通过比例
     - **Macro 通过率**：按 query 维度，每条 query 内全部约束通过才算该 query 通过
     - **Final Pass Rate**：全部约束通过的 query 比例
   - 每项约束的打分器必须是确定性代码（调用现有的契约校验/路线校验函数），**禁止用 LLM 当评委**做硬约束判定
2. 输出：评测结果写入 `backend/evals/results/YYYY-MM-DD.json`，并在终端打印三级指标汇总表。
3. 将评测脚本接入 `skills/travelmind-test` 工作流，作为"每周质量回归"或手动触发的可选步骤（不并入每小时冒烟，因为有 LLM 成本）。
4. 在 `README.md` 增加"质量评测"小节，说明指标含义与运行方式。

验收：
- [ ] `python -m backend.evals.run_evals`（或等价命令）可运行并输出 Micro/Macro/Final 三级指标
- [ ] 结果 JSON 落盘，包含每条 query 的逐项约束明细
- [ ] 基线三级指标记录进 `docs/BASELINE.md`
- [ ] 评测 query 全部来自数据文件，脚本内零硬编码

---

### Phase 3（P1）：会话持久化 —— Redis 外置，解除单 worker 限制

**背景**：`dialog_manager.py` 的 `_sessions` 是进程内字典（TTL 2h），README 自述"必须单 worker 运行、重启丢会话"，是当前最大架构债。

任务：
1. 抽象会话存储接口（如 `SessionStore` 协议/基类：`get`/`set`/`delete`/`touch`，值即对话状态），让 `dialog_manager.py` 只依赖接口。
2. 提供两个实现：
   - `InMemorySessionStore`：保留现有行为，作为无 Redis 环境下的默认/降级方案
   - `RedisSessionStore`：基于 `redis-py`（async），TTL 2h 与现状一致；连接配置走 `.env`（新增 `REDIS_URL`，同步更新 `.env.example`）
3. 通过环境变量切换实现（如 `SESSION_STORE=redis|memory`，默认 memory，保证离线开发可跑）。
4. 补充单元测试（可用 fakeredis 或 mock）：写入/读取/TTL 过期/进程重启后恢复（用两个 store 实例模拟）。
5. 更新 `README.md` 部署约束小节：说明多 worker 前提已解除及 Redis 配置方法。

验收：
- [ ] 设置 `SESSION_STORE=redis` 后，重启后端进程，进行中的对话会话不丢失（给出手动验证步骤或自动化测试）
- [ ] `SESSION_STORE=memory` 时行为与现状完全一致，契约回归全绿
- [ ] uvicorn 多 worker（`--workers 2`）下冒烟测试通过
- [ ] `.env.example`、`README.md` 已同步

---

### Phase 4（P1）：pytest 单元测试补齐 + CI

**背景**：项目没有任何单元测试（`backend/tests/` 不存在），现有"测试"全是需起服务的脚本级冒烟/E2E。`dialog_manager.py` 本身就按"可单测"设计，补单测成本最低、收益最大。

任务：
1. 新建 `backend/tests/`，用 pytest 补齐核心纯逻辑模块的单元测试（不依赖外部 API 的部分）：
   - `dialog_manager.py`：槽位收敛、确认流转、修改分流、追问轮次上限（≤3 轮）、TTL 过期
   - `itinerary_contract.py`：合法行程通过、各类非法行程（缺字段/类型错/天数不符/预算溢出）被正确拒绝
   - 推荐评分逻辑：Preference+Trend+Budget+Location+Context 的评分模型（PDR 第 85.4 条），含边界值
   - LLM/高德/天气等外部调用一律 mock
2. 配置 `pytest.ini`/`pyproject.toml` 与覆盖率（`pytest-cov`），核心模块行覆盖率目标 ≥70%。
3. 加 GitHub Actions CI（`.github/workflows/ci.yml`）：push/PR 时跑 pytest + 前端 `tsc --noEmit` 与 lint。LLM 契约回归不进 CI（有成本），保持本地/定时运行。
4. `README.md` 增加测试运行说明。

验收：
- [ ] `cd backend && pytest` 全绿，核心三模块覆盖率 ≥70%
- [ ] CI 配置存在且本地模拟（或直接推送验证）通过
- [ ] 全部测试不发起真实外部 API 请求（可用 `pytest -m "not external"` 或 socket 禁用手段证明）

---

### Phase 5（P1）：Docker 部署制品

任务：
1. `backend/Dockerfile`：Python 3.11 slim，安装依赖，uvicorn 启动；`.dockerignore` 排除 `.env`、`__pycache__`、Chroma 持久化目录（用 volume 挂载）。
2. `frontend/Dockerfile`：Node 18 构建 + nginx 托管静态产物，nginx 反代 `/api` 到 backend。
3. 根目录 `docker-compose.yml`：backend + frontend + redis +（可选）postgres 一键编排；Chroma 数据与 `backend/data/` 用 volume 持久化；环境变量统一从根目录 `.env` 读取。
4. 写 `docs/DEPLOY.md`：从零部署步骤、常用命令、排错清单。

验收：
- [ ] `docker compose up --build` 后，前端可访问、完整对话→生成行程→校验报告链路可走通（可用一条 curl/脚本验证后端健康检查与行程生成接口）
- [ ] 容器重启后 Chroma 数据与会话（Redis）不丢
- [ ] `docs/DEPLOY.md` 步骤可由他人照做复现

---

### Phase 6（P1）：用户体系与历史行程落库（PostgreSQL）

**背景**：`database/models.py` 存在但基本未用，用户/历史/收藏均无落库。这是"真正能帮助用户"的基础设施——没有历史，就没有个性化沉淀。

任务：
1. 完善 SQLAlchemy 模型：`users`（支持匿名 device_id 与注册账号两种形态，避免一上来做重注册流程）、`itineraries`（关联用户，存行程 JSON + validation_report + 画像快照 + 创建/修改时间）、`favorites`（收藏景点/行程）。
2. 用 Alembic 管理迁移，提供初始 migration；`.env` 增加 `DATABASE_URL`，`.env.example` 同步；无数据库时降级为现有行为（离线可跑的红线不变）。
3. 新增 API：`GET /api/v1/itineraries`（历史列表）、`GET /api/v1/itineraries/{id}`（详情）、`POST /api/v1/favorites` / `DELETE /api/v1/favorites/{id}`；生成行程时自动落库。
4. 前端：对话页/行程页增加"我的行程"入口与历史列表页；行程卡片加收藏按钮。
5. 隐私红线：日志与返回值中不得泄露他人行程；匿名用户之间以 device_id 隔离。

验收：
- [ ] 迁移命令可执行，表结构与设计一致
- [ ] 生成一条行程后可在"我的行程"中查到，刷新/重启后端不丢
- [ ] 收藏/取消收藏接口与前端可用
- [ ] 未配置 `DATABASE_URL` 时全功能降级正常，契约回归全绿

---

### Phase 7（P1）：真实价格层（区间价 + 来源时间戳 + 跳转预订）

**背景**：81% 用户人工复核 AI 行程的主因是价格不可信。不与 OTA 拼实时库存，先做"有出处、有时效"的价格。

任务：
1. 知识库景点数据扩展价格字段：`price_range`（区间）、`price_source`、`price_updated_at`（更新 `backend/data/attractions.json` 结构与加载逻辑；门票为 0 的免费景点显式标注"免费"而非留空）。
2. 行程生成时：每个 POI 展示区间价 + "价格更新于 X" 时间戳；行程汇总页给出总预算估算区间，并与用户预算槽位比对，超预算时给出明确提示与替代建议。
3. 每个 POI 增加"去预订/去看实时价"跳转链接（高德地图 POI 页或大众点评/美团搜索链接，做通用 deeplink 即可，不接私有 API）。
4. 前端在行程卡片与时间轴上展示上述价格信息，过期价格（如 >90 天未更新）标注"可能已变动"。

验收：
- [ ] 生成的行程中每个 POI 有区间价（或"免费"标注）+ 时间戳 + 跳转链接
- [ ] 总预算估算区间可见，超预算有提示
- [ ] 价格数据全部来自数据文件，代码零硬编码；契约回归全绿

---

### Phase 8（P2）：智能边界与行程版本化

任务（相互独立，可按序或挑选执行）：
1. **拒答机制（拒答优于编造）**：当 RAG 检索证据不足、目的地超出知识库覆盖（15 城之外）、或需求不可行（如"一天逛完北京 20 个景点"）时，意图层明确拒答或降级提示"该目的地数据有限，以下建议未经完全校验"，而不是硬生成。在 `dialog_manager.py` 或 orchestrator 入口处实现，附单元测试。
2. **扰动重规划**：行程交付后，若某 POI 在校验中发现已关闭，自动触发该时段的局部重规划（复用现有局部重生成能力），并向用户说明"XX 已关闭，已为您替换为 YY"。
3. **行程版本化**：行程快照版本链——每次局部修改生成新版本（父版本指针 + diff 摘要），前端可查看修改历史并回滚；存储依赖 Phase 6 的 itineraries 表扩展版本字段。

验收：
- [ ] 知识库外目的地提问时得到明确降级/拒答提示，而非编造行程（附测试用例）
- [ ] 模拟 POI 关闭场景可触发自动局部替换并有用户提示
- [ ] 同一行程连续修改 3 次后，可查看 3 个版本并回滚到任一版本

---

### Phase 9（P2）：数据持续化 —— POI 存续自动巡检

任务：
1. 写 `backend/scripts/poi_health_check.py`：遍历知识库 POI，调用高德接口核查存续状态与基础信息变更，输出巡检报告（`backend/data/poi_health_YYYY-MM-DD.json`），把失效 POI 标记为 `inactive`（不直接删除）。
2. 巡检结果反馈到生成层：inactive POI 不参与推荐。
3. 提供接入定时任务（cron）的运行说明，写进 `README.md` 或 `docs/DEPLOY.md`。

验收：
- [ ] 巡检脚本可运行并输出报告；失效 POI 被标记且不再出现在推荐结果中
- [ ] 报告落盘为数据文件；脚本内零硬编码 POI 列表

---

## 第四部分：执行顺序与依赖关系

```
Phase 0（文档基线）
  └─→ Phase 1（校验报告可视化）        ← 最高价值，先做
  └─→ Phase 2（评测体系）              ← 与 Phase 1 并行或紧随其后
        └─→ 后续所有 Phase 完成后都应重跑 Phase 2 评测，指标不得劣化
Phase 3（Redis）→ Phase 4（单测+CI）→ Phase 5（Docker）
Phase 6（用户体系）→ Phase 8.3（版本化）
Phase 7（价格层）可与 Phase 3–6 并行
Phase 8.1/8.2、Phase 9 独立，最后做
```

**给 Kimi Code 的总目标（/goal 一句话版）**：
> 按照 `docs/KIMI_CODE_GOAL_PROMPT.md` 的通用约束与 Phase 定义，把 TravelMind Agent 从"可演示 Demo"推进为"可信、可量化、可部署的旅行规划产品"：优先完成校验报告可视化（Phase 1）与质量评测体系（Phase 2），每个 Phase 必须验收全绿、回归不劣化，方可进入下一阶段。
