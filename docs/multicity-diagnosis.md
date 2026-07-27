# Multi-City 分类诊断（Phase 12.17）

> 日期：2026-07-25 · 数据来源：`evals/results/2026-07-25-phase12_16-v3.json` + 代码走读

## 现状

multi-city 分类 5 条 query，通过 2 条（m04/m05），失败 3 条。评测路径：
`POST /api/v1/recommend`（`run_evals.py:552`），不打行程生成，只看推荐列表。

## 失败明细与根因

### m01「推荐美食」— 无推荐结果（3 项约束全挂）

- **现象**：`places=[]`，http 200 或 422。
- **根因（链路：recommend.py:171-213）**：multi-city 分支要求 `tags` 非空才进入
  `retrieve_cross_city`。裸 query「推荐美食」经 Profile 提取后若 `destination` 为空
  且 `tags` 为空（LLM 对极短输入提取不稳定），直接落 422；
  或 tags 有值但 `retrieve_cross_city(tags=["美食"], top_k=30)` 语义检索
  召回为空/过少。
- **修复方向**：① Profile 提取兜底——输入含「美食」等明确品类词时由代码侧
  正则补充 tags（不依赖 LLM）；② `retrieve_cross_city` 召回为空时降级为
  按 tag one-hot 精确匹配 + popularity 排序的确定性兜底。

### m02「想看海，哪里比较好」— 只召回三亚（城市数=1，阈值 3）

- **现象**：候选全部来自三亚，`cross_city_covered` / `multi_city_diversity` 失败。
- **根因（2026-07-25 实测修正）**：不是检索召回问题——Profile LLM 把模糊查询
  猜测为「三亚」，`recommend.py` 走了单城路径，`retrieve_cross_city` 根本没被调用。
- **修复（已实施）**：`recommend.py` 发现式查询识别——LLM 猜出的目的地未在
  用户原文出现，且原文含「哪里/哪个/哪些/去哪/什么地方/推荐」时，强制多城路径。
- **附带加固（已实施）**：`retriever.py` `retrieve_cross_city` 在语义召回 <3 城时
  按城市配额补充检索（每城 top 3，最多补至 6 城），跨城多样性成为结构性保障。

### m03「适合情侣去的浪漫旅行地」— min_score_filter 47%（阈值 60%）

- **现象**：30 条结果中 score≥0.35 仅 14 条。
- **根因（recommend.py:195）**：multi-city 分支调 `recommend(profile, candidates, trends=None)`，
  7 因子公式中 Trend_Heat 权重 0.25 因 trends=None 基本归零，
  分数上限被压到 ~0.75 区间，大批候选落在 0.35 之下。
- **修复方向**：跨城路径构造一个合成 trends（按城市取各城 top 趋势景点的
  heat 均值），或对 multi-city 路径的 Trend_Heat 缺失做权重再归一化
  （把 0.25 权重按比例分给其余因子），避免系统性低分。

## 优先级建议

m02 > m01 > m03。m02 是检索结构性问题，修复后对真实用户价值最大
（"想看海"类模糊查询是推荐场景的高频输入）。
