---
name: travelmind-data
description: |
  TravelMind Agent 知识库数据管线：室内覆盖率统计、社交候选采集（WebSearch/WebBridge）、
  OSM 验证合并、Chroma 重建、数据质量报告。
  当用户说"补充数据 / 扩充知识库 / 采集 POI / 数据质量 / 重建向量库"，或评测暴露某城市数据缺口时使用本技能。
  🔴 数据铁律：所有数据必须可追溯真实来源；社交来源只出热度信号，事实字段（坐标/存在性）
  必须经 OSM/高德验证，无验证不入库；禁止 AI 编造任何字段。
---

# TravelMind 数据管线

## 单入口（优先使用）

```bash
cd backend && python scripts/build_kb.py                    # 全管线
cd backend && python scripts/build_kb.py --skip fetch-osm   # 仅合并+重建+质检
cd backend && python scripts/build_kb.py --only normalize,rebuild,quality
```

7 阶段：coverage → fetch-osm → merge → verify-social → normalize → rebuild → quality。
幂等可重跑（合并按「标准化名称+城市」去重）。

## 分步脚本（需要单步执行时）

| 步骤 | 脚本 | 说明 |
|------|------|------|
| 覆盖率统计 | `scripts/indoor_coverage_report.py` | 各城市室内 POI 占比，<35% 输出低覆盖清单 |
| OSM 室内采集 | `scripts/fetch_indoor_osm.py [--cities 武汉,郑州]` | Overpass API，免费，bbox 自动钳制中位数±0.4° |
| 社交热度采集 | `scripts/collect_social_webbridge.py [--platform douyin] [--cities ...]` | 小红书/抖音（需 WebBridge + 浏览器登录态），标题匹配 KB → heat_score；未匹配名 → 候选文件 |
| 候选验证合并 | `scripts/verify_merge_social_pois.py [--dry-run]` | OSM 逐条验证后才入 KB，拒绝进报告 |
| 通用合并 | `scripts/merge_indoor_pois.py --input <file>` | 采集文件 → attractions.json |
| 质量报告 | `scripts/data_quality_report.py` | 来源分布/字段完整率/室内覆盖率/价格时效 |

## 关键教训（2026-07 数据污染复盘，勿再犯）

- OSM 名称匹配**只允许**：标准化相等，或候选名（≥4 字符）⊆ OSM 名；**绝不允许反向包含**
  （"武汉博物馆" ⊂ "不妨去武汉博物馆"这类标题片段会误判通过）
- 纯泛称（"博物馆"/"美术馆"/"图书馆"等）永远拒绝，即使 OSM 里真有叫这个名字的地物
- 验证脚本先 `--dry-run` 看报告再正式合并
- 社交采集脚本是**合并写入**，零产出不会清空历史趋势数据

## 数据源可用性（2026-07-26 实测）

- OSM Overpass ✅（事实主力源）；WebSearch ✅（候选发现）；WebBridge ✅（需用户浏览器在线）
- 高德 ⚠️ AMAP_API_KEY 为空；Wikidata/Nominatim ❌ GFW 阻断
- 当前 KB：**2,410 POI / 30 城市**（Phase 12.27），pytest 373 全过（21 文件）

## 收尾

数据变更后必须：`bash scripts/backend_restart.sh --rebuild`，然后用 travelmind-eval 技能跑 standard 快验确认不回退。
