# TravelMind Agent — 优化方向（2026-07-27 Autofix Phase 7）

> 自动生成于 autofix 循环 Phase 7，基于多维扫描结果。

## 本轮修复（1 项 P1）

| 问题 | 文件 | 修复 |
|------|------|------|
| 非流式错误路径泄露 str(e) | `chat.py:116`, `agent.py:279` | 替换为通用错误消息 |

## 遗留 P2 项（可延后）

| 项 | 位置 | 说明 | 预估工作量 |
|---|------|------|-----------|
| 前端 api.ts 死代码 | `frontend/src/lib/api.ts` | 13 个未使用的类型导出 + axios 实例暴露 | 小（~15min）|
| 后端函数内 import | app/ 下 8 处 | 标准库 import 在函数体内，应提升到模块级 | 小（~20min）|
| A11Y 全站扫描 | 全局 | ImageUploader 已修，但全站其他组件未审计 | 中（~2h）|

## 下一轮方向（按优先级）

### 🥇 P1 — 测试体系扩展（强烈推荐）

| 覆盖缺口 | 当前 | 建议 |
|---------|------|------|
| agent 无测试 | 10 agents 中 4 个无专用测试（chat_agent、profile_agent、trend_agent、vision_agent） | 每 agent 至少 1 个 smoke test |
| service 无测试 | 15 services 中 6 个无测试（amap、llm_service、vision_service、weather_cache、poi_health、itinerary_version） | 每 service 至少 1 个错误降级 test |
| 当前总数 | 22 文件 373 test | 目标：400 test |

**推荐命令：** `/travelmind-autofix --focus backend`

### 🥈 P2 — 数据缺口

当前 KB 2,321 POI / 30 城市，部分品类和城市覆盖率偏低：
- 部分室内 POI 较少城市需二次 OSM 采集
- AMAP_API_KEY 恢复后可跑 `enrich_indoor_amap.py`
- 上海美食已 9 类（Phase 12.22），其他城市可参照扩充

**推荐命令：** 需人工填入 AMAP_API_KEY 后执行 `/travelmind-autofix --focus ops`

### 🥉 P2 — 技术债务

- **依赖升级**：检查 requirements.txt 各库是否到最新兼容版本
- **Python 版本**：当前 3.10，可选升级到 3.11+
- **TypeScript**：当前 strict:true 已开启，但仍有 13 个类型可降为内部

**推荐命令：** `/travelmind-autofix --quick`（快速验证 + 文档更新）

## 评测现状

- **基线**：12.28 v3（80 queries × 28 约束）
- **Micro**：83.7% / **Macro**：61.3%（49/80）
- **当前为纯代码质量阶段**，未跑新评测
- Phase 12.30 开始可跑全量评测建立新基线
