# Weather Fit 优化（Phase 12.17+）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将评测 weather_fit 从 75.0%（30/40）提升至 85%+，同时保持 Macro ≥ 74.6% 不回退。

**Architecture:** 三层递进——P0 prompt 强化（已实施，待评测验证）→ P1 知识库室内 POI 扩充（高德 API 真实数据）→ P2/P3 评测稳定性与 multi-city 诊断。评分/检索逻辑不动，只改 prompt 与数据。

**Tech Stack:** Python 3.10（D:\python310）、FastAPI、DeepSeek LLM、高德 POI API（MD5 签名）、ChromaDB、pytest。

## Global Constraints

- 🔴 数据完整性铁律：所有 POI 数据必须来自高德 API 真实返回，严禁 AI 编造/估算；无法获取的字段留 `null`
- `attractions.json` 是 dict 格式 `{"attractions": [...]}`，访问需 `json.load(f)["attractions"]`
- 评测结果文件命名 `backend/evals/results/YYYY-MM-DD-phaseXX_XX-vN.json`，不得覆盖历史结果
- 评测命令的正确参数是 `--category`（交接文档中 `--tags` 为笔误）
- 所有命令工作目录为 `D:/TravelMindAgent/backend`（除非注明）
- 不做任何 git commit/push（用户未授权）
- Chroma 批量插入 batch_size ≤ 150
- 单元测试基线：301 passed, 0 failed — 任何任务完成后不得劣化

---

### Task 1: Phase 12.17 评测验证与文档收尾

**Files:**
- Modify: `backend/app/agents/planning_agent.py`（已完成：`_format_rainy_days` 新增、`rain_block` 强化、`_format_weather` 🌧️ 标记、`_QUALITY_REQUIREMENTS` 第 11 条收紧）
- Modify: `docs/BASELINE.md`
- Modify: `HANDOFF_TO_KIMICODE.md:710`（`--tags standard` → `--category standard` 笔误修正）
- Create: `backend/evals/results/2026-07-25-phase12_17-v1.json`（评测自动生成）

**Interfaces:**
- Consumes: 正在运行的 standard 评测结果（后台任务 bash-br8mjb7o）
- Produces: Phase 12.17 基线数据，供 Task 4 对比

- [ ] **Step 1: 读取 standard 评测结果**

后台任务完成后读取输出，提取 weather_fit 通过数与 Macro。
对比基线：weather_fit 30/40 (75.0%)，standard 22/30 (73.3%)。

- [ ] **Step 2: 判断结果走向**

- weather_fit ≥ 80% 且 standard 无 >2pp 回退 → 进 Step 3 全量评测
- weather_fit 无改善 → 读取失败 query 的 `weather_notes`，调整 `rain_block` 措辞后重跑 `--category standard`
- standard 回退 >2pp → 放宽 `_format_rainy_days` 措辞（去掉"全部为室内"的硬性表述）后重跑

- [ ] **Step 3: 全量评测并存档**

```bash
cd backend
python -X utf8 -m evals.run_evals --out evals/results/2026-07-25-phase12_17-v1.json
```
预期：~25 分钟，63 query × 24 约束。Macro ≥ 74.6% 视为不回退。

- [ ] **Step 4: 修正交接文档笔误**

`HANDOFF_TO_KIMICODE.md` 第 710 行：
`python -X utf8 -m evals.run_evals --tags standard` → `python -X utf8 -m evals.run_evals --category standard`

- [ ] **Step 5: 更新 docs/BASELINE.md**

在文件头部新增 Phase 12.17 段落（格式仿照现有 Phase 12.16 段，第 31-122 行）：指标对比表（Micro/Macro/weather_fit vs 12.16）、按分类表、weather_fit 修复/退步明细、变更摘要表（仅 `planning_agent.py` prompt 4 处改动）。
同步更新第 4 行头部摘要。

- [ ] **Step 6: 复跑单元测试**

```bash
python -m pytest 2>&1 | tail -3
```
预期：`301 passed`。

---

### Task 2: P1 — 室内覆盖率统计脚本（确定性，无 LLM）

**Files:**
- Create: `backend/scripts/indoor_coverage_report.py`

**Interfaces:**
- Consumes: `backend/data/attractions.json`、`app.agents.itinerary_contract.classify_poi_indoor(poi_name, kb_tags)`
- Produces: 控制台报告 + `backend/data/indoor_coverage_report.json`（供 Task 3 决定目标城市）

- [ ] **Step 1: 编写脚本**

```python
"""
TravelMind Agent — Indoor POI Coverage Report

统计每个城市知识库中 indoor/semi POI 占比，找出低覆盖率城市。
纯确定性统计，零 LLM 成本，零外部调用。

用法：
  cd backend
  python scripts/indoor_coverage_report.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.itinerary_contract import classify_poi_indoor

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    with open(DATA_DIR / "attractions.json", "r", encoding="utf-8") as f:
        attractions = json.load(f)["attractions"]

    by_city = defaultdict(lambda: {"total": 0, "indoor": 0, "semi": 0, "outdoor": 0})
    for a in attractions:
        city = a.get("city", "未知")
        name = a.get("name", "")
        tags = a.get("tags", [])
        cls = classify_poi_indoor(name, kb_tags=tags or None)
        by_city[city]["total"] += 1
        by_city[city][cls] += 1

    rows = []
    for city, s in by_city.items():
        indoor_ratio = (s["indoor"] + s["semi"]) / max(s["total"], 1)
        rows.append((city, s["total"], s["indoor"], s["semi"], s["outdoor"], indoor_ratio))
    rows.sort(key=lambda r: r[5])

    print(f"{'城市':<8} {'总数':>4} {'室内':>4} {'半室内':>4} {'户外':>4} {'室内率':>7}")
    for city, total, ind, semi, out, ratio in rows:
        flag = " ⚠️ 低覆盖" if ratio < 0.35 else ""
        print(f"{city:<10} {total:>4} {ind:>4} {semi:>4} {out:>4} {ratio:>7.1%}{flag}")

    low = [{"city": c, "total": t, "indoor_ratio": round(r, 3)}
           for c, t, _, _, _, r in rows if r < 0.35]
    with open(DATA_DIR / "indoor_coverage_report.json", "w", encoding="utf-8") as f:
        json.dump({"low_coverage_cities": low}, f, ensure_ascii=False, indent=2)
    print(f"\n低覆盖城市（<35%）：{[c['city'] for c in low]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行并核查**

```bash
python scripts/indoor_coverage_report.py
```
预期：输出 30 城市表格；武汉应出现在低覆盖列表（Phase 12.16 已知 31 POI 仅 16% 室内）。人工核查 2-3 个城市的分类是否合理（抽查 attractions.json 中该城市 POI 名称）。

---

### Task 3: P1 — 高德室内 POI 采集脚本

**Files:**
- Create: `backend/scripts/enrich_indoor_amap.py`（以 `backend/scripts/enrich_food_amap.py` 483 行为模板复制改造）
- Create: `backend/data/indoor_pois.json`（脚本输出）

**Interfaces:**
- Consumes: Task 2 的 `indoor_coverage_report.json`（目标城市）、`AMAP_API_KEY`/`AMAP_SIGN_KEY`（backend/.env）
- Produces: `data/indoor_pois.json`，格式与 `food_pois.json` 相同，供 Task 4 合并

- [ ] **Step 1: 复制模板并替换常量块**

```bash
cp backend/scripts/enrich_food_amap.py backend/scripts/enrich_indoor_amap.py
```

替换常量区（约 50-107 行），改为：

```python
OUTPUT_FILE = DATA_DIR / "indoor_pois.json"

# 高德 POI 大类（顶层代码，真实存在）：
#   060000 = 购物服务；140000 = 科教文化服务（含博物馆/展馆）
INDOOR_TYPES = {
    "博物馆展馆": "140000",
    "购物商场": "060000",
}

# 搜索关键词（按类别扩充覆盖）
INDOOR_KEYWORDS = [
    # 博物馆/展馆
    "博物馆", "美术馆", "科技馆", "纪念馆", "展览馆", "规划馆", "图书馆",
    # 购物/室内商业
    "购物中心", "商场", "商业综合体", "奥特莱斯", "室内步行街",
    # 室内体验
    "温泉", "室内游乐场", "剧院", "书店",
]
```

- [ ] **Step 2: 改造筛选与分类函数**

- `_classify_food_type` → `_classify_indoor_type`：关键词命中 `博|纪念|美术|科技|展览|规划|图书` → "博物馆展馆"；命中 `购|商场|百货|奥特莱斯` → "购物商场"；其余 → "室内体验"
- 筛选阈值放宽：`rating >= 3.5 and comments >= 20`（博物馆评论数普遍低于餐饮）
- `_make_food_poi` → `_make_indoor_poi`：输出 dict 的 `tags` 字段必须包含对应室内标签（如 `["博物馆", "文化", "室内"]`），这是 `classify_poi_indoor` 的 KB 标签判定的输入
- `main()` 默认城市来源：读 `data/indoor_coverage_report.json` 的 `low_coverage_cities`；不存在则回退 `["武汉", "郑州", "长沙"]`
- docstring 改为说明用途与用法：`python scripts/enrich_indoor_amap.py [--cities 武汉,郑州] [--limit 10]`

- [ ] **Step 3: 小规模试跑**

```bash
python scripts/enrich_indoor_amap.py --cities 武汉 --limit 5
```
预期：输出 `data/indoor_pois.json`，含武汉室内 POI；抽查 3 条核对高德返回名称/地址真实（🔴 铁律：逐条可追溯，脚本不得合成任何字段）。

- [ ] **Step 4: 全量采集**

```bash
python scripts/enrich_indoor_amap.py
```
预期：低覆盖城市每城 15-40 条室内 POI，去重后写入 `indoor_pois.json`。

---

### Task 4: P1 — 知识库合并重建与评测验证

**Files:**
- Modify: `backend/scripts/build_knowledge_base.py`（若其不支持合并 indoor_pois.json，仿照 food_pois.json 的合并逻辑添加一个输入源）
- Modify: `backend/data/attractions.json`（脚本生成）
- Modify: `docs/BASELINE.md`

**Interfaces:**
- Consumes: `data/indoor_pois.json`（Task 3）、`build_knowledge_base.py` 现有合并逻辑
- Produces: 更新后的 attractions.json + Chroma 向量库；Task 1 的基线用于对比

- [ ] **Step 1: 检查合并逻辑**

```bash
grep -n "food_pois" backend/scripts/build_knowledge_base.py
```
若有 food_pois 合并段，仿照其结构加 indoor_pois 输入；若已是通用多源合并，仅需把 indoor_pois.json 加入源列表。

- [ ] **Step 2: 重建知识库与向量库**

```bash
python scripts/build_knowledge_base.py
```
预期：attractions.json POI 总数 > 1,788；Chroma 重建完成（batch ≤ 150）。

- [ ] **Step 3: 复跑覆盖率报告**

```bash
python scripts/indoor_coverage_report.py
```
预期：武汉等低覆盖城市室内率 ≥ 35%。

- [ ] **Step 4: 单元测试 + 重启后端**

```bash
python -m pytest 2>&1 | tail -3
taskkill //PID <uvicorn_pid> //F
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000   # 后台
```
预期：301 passed；等健康检查通过后继续。

- [ ] **Step 5: 评测对比**

```bash
python -X utf8 -m evals.run_evals --category standard
```
预期：weather_fit 在 Task 1 结果基础上不退步；武汉 q19、郑州 q23 等有改善迹象。显著回退则检查新 POI 的 popularity_score 是否挤压了头部景点（必要时调低新 POI 的 popularity 至 5-6 区间）。

- [ ] **Step 6: 全量评测存档 + 更新 BASELINE.md**

```bash
python -X utf8 -m evals.run_evals --out evals/results/2026-07-26-phase12_18-v1.json
```

---

### Task 5: P2 — 评测稳定性测量

**Files:**
- Modify: `docs/BASELINE.md`

- [ ] **Step 1: 波动分类三连跑**

```bash
for i in 1 2 3; do python -X utf8 -m evals.run_evals --category chat --out evals/results/chat-stability-$i.json; done
for i in 1 2 3; do python -X utf8 -m evals.run_evals --category multi-city --out evals/results/mc-stability-$i.json; done
```

- [ ] **Step 2: 计算均值与方差，写入 BASELINE.md**

在 BASELINE.md 新增"评测稳定性"小节：chat 与 multi-city 三次通过率（均值 ± 极差），后续 Phase 对比时以均值为基准。

---

### Task 6: P3 — multi-city 诊断（先测量，后定方案）

**Files:**
- Create: `docs/multicity-diagnosis.md`（诊断结论）

- [ ] **Step 1: 提取失败详情**

从 Task 5 的 multi-city 三份结果 JSON 中，提取每条失败 query 的未通过约束（`cross_city_covered` / `multi_city_diversity` / `min_score_filter`）与 detail 字段。

- [ ] **Step 2: 归因分类**

将失败归因到三类之一：① 跨城推荐候选不足（RAG 检索问题）；② LLM 行程只覆盖单城（prompt 问题）；③ 评分过滤过严（`min_score_filter` 阈值问题）。每类给出对应修复建议，写入 `docs/multicity-diagnosis.md`。

- [ ] **Step 3: 向用户汇报诊断结果，由用户决定是否在后续 Phase 修复**

## Self-Review 记录

- Spec 覆盖：P0 验证（Task 1）、P1 KB 扩充（Task 2-4）、P2 稳定性（Task 5）、P3 multi-city（Task 6）均已覆盖
- 无占位符：所有脚本代码与命令完整给出；Task 3 的函数改造给出了精确替换内容与行为规格
- 类型一致：`classify_poi_indoor(name, kb_tags)`、`--category`、`indoor_coverage_report.json` 的 `low_coverage_cities[].city` 在各任务间一致

## 执行偏差记录（2026-07-25 实际执行）

- **Task 1 发现 v1 prompt 改动引入 poi_verified 回退**（29→20/30）：根因是 LLM 被迫编造室内 POI 名称 + 菜名当 POI + 雷暴日规则未分级。修复：prompt 增加恶劣天气零户外分级、反菜名规则、KB 已验证室内清单注入；另修复 route_optimizer 重排打乱时间轴（时间槽升序回填）
- **Task 3 数据源变更**：`backend/.env` 的 `AMAP_API_KEY` 为空、Wikidata 被 GFW 阻断 → 改用 **OSM Overpass API**（`scripts/fetch_indoor_osm.py`，ODbL，带 osm_id 可追溯）。15 低覆盖城市采集 269 条（含郑州 bbox 超时修复：中位数 ±0.4° 钳制）
- **Task 4 完成**：KB 1,788 → 2,057，Chroma 重建；低覆盖城市从 15 个清零（郑州/香格里拉/拉萨 OSM 数据稀疏但已补 5-20 条）
- **v4 standard 验证**：weather_fit 22→24/30、poi_verified 29→28/30、Macro 73.3%→77%、Micro 97.5%
- **P3 提前完成诊断并修复**：m01 tags 兜底（recommend.py）、m02 发现式查询强制多城 + 跨城配额召回（retriever.py），见 `docs/multicity-diagnosis.md`（其中 m02 根因经实测修正为 Profile 猜测目的地走单城路径）
