---
name: scan-findings-phase12-29
description: Phase 12.29 优化扫描汇总 — 三线扫描共发现 132 项优化点（2026-07-27）
metadata: 
  node_type: memory
  type: project
  originSessionId: 7b4f2bb5-2f5d-478e-b624-d3334b9a4338
  modified: 2026-07-27T01:15:35.847Z
---

# Phase 12.29 优化扫描汇总

三线并行 agent 扫描结果：**后端 46 项 + 前端 38 项 + 架构/DevOps 48 项 = 132 项**。

## 已修复（当前会话）

- ✅ `run_evals.py` 缺少 `Tuple` 导入 → 评测启动报错
- ✅ `main.py` 未集成 `RateLimitMiddleware`（Phase 12.28c 遗漏）
- ✅ `main.py` 未注册 `api_error_handler`（Phase 12.28c 遗漏）
- ✅ `weather_service.py` 未集成 `WeatherCache` L1 快速缓存（Phase 12.28c 遗漏）
- ✅ 项目根目录缺少 `CLAUDE.md`（Claude Code 原生上下文机制未用）

## HIGH 优先级 (21 项)

### 后端 HIGH (14 项)

| ID | 类别 | 问题 |
|----|------|------|
| H1 | 重复 | `connection.py` 和 `deps.py` 有两个 `get_db` |
| H2 | 错误处理 | `itineraries.py` 的 `_get_user_id` 在 db=None 时崩溃 |
| H3 | 并发 | `get_llm_provider()` 单例无锁 |
| H4 | 逻辑 | `user_service.py` 的 `last_active_at` 从未更新 |
| H7 | 性能 | `models.py` 缺少 FK 索引（user_id 列） |
| H9 | 安全 | `X-Device-ID` 无验证直接用作身份 |
| H10 | 安全 | 所有 API 端点无认证 |
| H12 | 测试 | 零 HTTP 层集成测试 |
| H13 | 测试 | `weather_service`/`amap_service`/`llm_service`/`vision_service` 无测试 |
| H14 | 配置 | `APP_DEBUG` 默认为 `True` |
| H15 | 配置 | CORS origins 硬编码 |

### 前端 HIGH (4 项)

| ID | 问题 |
|----|------|
| 1.1 | `React.lazy` 代码分割缺失 |
| 1.2 | SSE reader 无 abort-on-unmount 清理 |
| 2.1 | `ErrorBoundary` 未在 App.tsx 使用 |
| 2.2 | ImageUploader 拖拽区不可键盘访问 |
| 3.1 | `html2canvas` + `jspdf` (~300KB) 未动态加载 |
| 10.1 | `strict: true` 缺失于 TypeScript 配置 |

### 架构/DevOps HIGH (7 项)

| ID | 问题 |
|----|------|
| 1.4 | 数据库迁移失败静默吞掉 |
| 1.5 | entrypoint 无 wait-for-DB 重试逻辑 |
| 3.1 | POI 健康检查因 AMAP_API_KEY 为空而无法运行 |
| 4.1 | 无 Prometheus `/metrics` 监控端点 |
| 6.1/10.1 | 无 `CLAUDE.md`（✅ 已修复） |

## 优化子阶段建议

### Phase 12.29a — 安全 + 配置加固（HIGH）
- APP_DEBUG 改为 False 默认
- CORS origins 配置化
- X-Device-ID 格式校验
- 限流 X-Forwarded-For 信任验证
- 流式错误信息脱敏

### Phase 12.29b — 测试体系扩展（HIGH）
- API HTTP 层集成测试
- 外部服务 mock 测试
- orchestrator/trend_agent/vision_agent 单测

### Phase 12.29c — 前端性能 + 可访问性（HIGH）
- React.lazy 路由级代码分割
- html2canvas/jspdf 动态导入
- SSE abort-on-unmount 清理
- ErrorBoundary 包裹根组件
- ImageUploader 键盘可访问
- TypeScript strict: true

### Phase 12.29d — 运维 + 监控（HIGH）
- Docker healthcheck 定义
- entrypoint wait-for-DB + 迁移失败 fast-fail
- Prometheus /metrics 端点
- 结构化日志

### Phase 12.29e — 代码质量统一（MEDIUM）
- 移除死代码/重复导入
- BUDGET_MAP/SEASON_MONTHS 集中化
- 统一错误格式（所有路由使用 error_response）
- 数据库索引补全

**Why:** 三线扫描暴露了大量低垂果实，优先级为安全 > 测试 > 性能 > 运维 > 代码整洁。

**How to apply:** 每个子阶段完成后运行 fixcycle.sh 验证。
