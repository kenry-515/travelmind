# TravelMind 数据全流程架构（DATA_PIPELINE）

> 版本：2026-07-25 · 状态：前期已落地，中后期为路线规划
> 铁律：🔴 所有数据必须可追溯真实来源；社交来源只出热度信号，事实字段（坐标/存在性）必须经 OSM/高德等结构化源验证，无验证不入库。

## 架构总览（五层一单入口）

```
获取层 Sources          清洗层 Clean         验证层 Verify        入库层 KB           运营层 Ops
┌──────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐
│ OSM Overpass(主力)│  │ 去重(norm+city)  │  │ 存在性交叉验证    │  │ build_kb.py   │  │ 覆盖率报告       │
│ WebBridge 登录态  │→ │ 噪音过滤(超市/   │→ │ 社交源只出热度    │→ │ 单入口编排     │→ │ 数据质量报告     │
│  小红书/抖音/点评 │  │  连锁/校园/泛称) │  │ 不出事实         │  │ →Chroma 重建  │  │ POI 存续巡检    │
│ WebSearch 热议    │  │ 分类归一(51标签) │  │ 拒绝全部进报告    │  │ 幂等可重跑     │  │ 评测回归门槛    │
│ 高德(额度恢复后)  │  │ 坐标合理性校验   │  │                 │  │              │  │ 月度更新节奏    │
└──────────────────┘  └─────────────────┘  └─────────────────┘  └──────────────┘  └─────────────────┘
```

## 单入口命令

```bash
cd backend
python scripts/build_kb.py                    # 全管线：coverage→fetch-osm→merge→fetch-food-osm→merge-food→verify-social→normalize→rebuild→quality
python scripts/build_kb.py --skip fetch-osm   # 仅合并+重建+质检
python scripts/build_kb.py --only normalize,rebuild,quality
```

## 各层职责与脚本映射

| 层 | 脚本 | 输入 → 输出 | 成本 |
|---|------|------------|------|
| 获取-OSM | `fetch_indoor_osm.py` | 低覆盖城市 → `data/indoor_osm.json` | 免费（Overpass 公共实例，1 req/s） |
| 获取-OSM 美食 | `fetch_food_osm.py`（Phase 12.22） | 城市 → `data/food_osm.json`（细分品类：小吃/面馆/早点/烧烤/火锅/海鲜/饮品甜点/国际美食） | 免费（镜像端点轮换防 504） |
| 获取-社交 | `collect_social_webbridge.py` | 城市列表 → `data/social_trends_live.json` + 新候选 | 免费（用户浏览器登录态） |
| 获取-WebSearch | 手动/子代理 | 城市列表 → `data/social_poi_candidates.json` | Kimi token 少量 |
| 获取-高德 | `enrich_food_amap.py` / `enrich_indoor_amap.py` | 城市 → food/indoor_pois.json | 高德配额（当前为空） |
| 清洗 | 各采集脚本内联 | 噪音/连锁/泛称过滤 | 零 |
| 验证 | `verify_merge_social_pois.py` | 候选 → OSM 验证 → 合并/拒绝报告 | 免费 |
| 入库-合并 | `merge_indoor_pois.py` | 采集文件 → attractions.json（去重幂等） | 零 |
| 入库-规范化 | `build_kb.py [normalize]` | 补齐 name_normalized 100% | 零 |
| 入库-重建 | `build_knowledge_base.py` | attractions.json → Chroma | 本地 TF-IDF，零 API |
| 运营-质量 | `data_quality_report.py` | attractions.json → 来源/完整率/覆盖率报告 | 零 |
| 运营-覆盖 | `indoor_coverage_report.py` | 室内覆盖率分城市统计 | 零 |
| 运营-巡检 | `poi_health_check.py` | POI 存续验证 | 高德配额（暂停） |

## 数据流细则

### 社交数据（热度信号通道）
1. `collect_social_webbridge.py` 驱动用户浏览器访问小红书/抖音搜索页（类目定向查询），提取笔记标题/点赞/链接
2. 标题与 KB 名称变体（原名/normalized/core）双向匹配 → 命中 KB POI 获得 `heat_score`（点赞 log 缩放 40-98），写入 `social_trends_live.json`（合并写入，零产出不清空历史）
3. 标题中未匹配的疑似 POI 名 → 追加到 `social_poi_candidates.json`
4. 候选经 `verify_merge_social_pois.py` 用 OSM 验证存在性和坐标后才入 KB
5. **社交源永远不直接写入 KB**——这是防止网红软文污染知识库的关键闸门

> ⚠️ 验证匹配规则（2026-07-25 数据污染事件复盘）：仅接受「标准化相等」或
> 「候选名(≥4字符) ⊆ OSM 名」。绝不允许反向包含（OSM 名 ⊆ 候选名）——
> 否则"武汉博物馆" ⊂ "不妨去武汉博物馆"这类标题片段会误判通过；
> 短泛称（"博物馆"等 <4 字符）禁止子串匹配。事件中共清除 9 条噪音条目。

> ⚠️ 平台限制（2026-07-25 实测）：小红书笔记正文页有反爬封锁
> （"当前笔记暂时无法浏览，请打开App扫码"），登录态网页端也无法读取正文。
> 当前只有搜索结果页（标题/点赞/链接）可采集；需要正文级数据时走
> 抖音/大众点评适配（中期路线）或 WebSearch 摘要。

> ⚠️ Overpass 容错（2026-07-26 加固）：主实例 504/429 高发时段，
> 旧版验证脚本曾把"查询失败"当"未找到"导致 143 条候选全城静默全拒。
> `verify_merge_social_pois.py` 现已加固：①三镜像端点轮换
> （overpass-api.de / kumi.systems / private.coffee）；②查询失败抛
> `OverpassUnavailable`，单城跳过、全城继续，报告单独立 `query_failed`
> 类（脚本幂等，重跑即补齐，退出码 2 提示）；③首轮 ±0.4° bbox 未命中者
> 用 ±0.8° 宽 bbox 二轮补查（覆盖远郊，如国家海洋博物馆距市区 40km）；
> ④支持 `--cities` 分块运行，验证报告按城市增量合并不丢历史去向。

### 趋势数据消费
- `trend_agent.py` 读 `data/trends.json`（389 条人工整理）
- `social_trends_live.json` 为实时补充源，格式兼容（city/place_name/heat_score/source/source_url）
- 中期：trend_agent 合并读取两个文件，实时热度优先

## 数据源可用性矩阵（2026-07-25 实测）

| 源 | 状态 | 用途 |
|---|------|------|
| OSM Overpass | ✅ 可用 | POI 事实（坐标/类型）主力源 |
| WebBridge（小红书） | ✅ 可用 | 社交热度 + 新 POI 发现 |
| WebSearch | ✅ 可用 | 社交热议候选收集 |
| Nominatim | ❌ 被 GFW 阻断 | — |
| Wikidata SPARQL | ❌ 被 GFW 阻断 | — |
| Wikipedia API | ⚠️ 需 wikimedia.org 代理 | 摘要富化 |
| 高德 Web 服务 | ⚠️ 额度耗尽（AMAP_API_KEY 空） | POI/路线/存续巡检（恢复后重启） |

## 分期路线

### 前期（已落地，2026-07-25）
- [x] 单入口 `build_kb.py`（7 阶段编排）
- [x] OSM 室内 POI 采集（269 条，15 低覆盖城市清零）
- [x] WebSearch 社交候选 + OSM 验证合并（26 条）
- [x] WebBridge 小红书热度采集（3 城跑通：标题-KB 双向匹配 + 点赞热度 + 来源 URL，趋势数据经 trend_agent 实时合并消费，实测 郑州博物馆 trend_heat=0.69 来自小红书点赞）
- [x] 社交候选 OSM 验证（累计 54 条入库，KB 2,057 → 2,111）
- [x] 数据质量报告（来源分布/字段完整率/覆盖率）
- [x] name_normalized 补齐至 100%
- [x] trend_agent 实时热度合并（social_trends_live.json 覆盖静态 trends.json 同名条目）

### 中期（1-2 周）
- [ ] 抖音/大众点评平台适配（页面结构不同，复用 WebBridge 框架）
- [ ] 45 条 OSM 未覆盖候选二次验证（高德恢复后，含国家海洋博物馆/深圳博物馆等）
- [ ] 字段补全：price_range 覆盖率 42% → 70%（OSM fee 标签 + 本地宝票价页）
- [ ] 拉萨/香格里拉室内覆盖率 <35%（OSM 数据稀疏，需 WebSearch 定向补充）

### 后期（月度节奏）
- [ ] 增量更新调度：每月跑 `build_kb.py`（社交热度刷新 + 新 POI 验证），每季度 POI 存续巡检
- [ ] 新城市扩展模板：城市名 → OSM 采集 → 社交热度 → 验证 → 入库，一键完成
- [ ] KB 版本化：每次 build 自动快照 `attractions.json.bak-YYYYMMDD`，支持回滚
- [ ] 数据质量门槛纳入 CI：完整率/覆盖率低于阈值时告警

## 成本结构

| 项 | 成本 | 说明 |
|---|------|------|
| OSM Overpass | 免费 | 公共实例限速 1 req/s，全量采集 ~15 分钟 |
| WebBridge | 免费 | 用户浏览器，无 API 费用；注意平台反爬，限速 3s/页 |
| WebSearch | 少量 token | 仅用于候选发现 |
| DeepSeek（AI 标注） | 按量付费 | 仅新增 POI 需要 tags 富化时使用，批次 25 |
| 高德 | 按量付费 | 当前停用；恢复后用于存续巡检与精确地理编码 |
