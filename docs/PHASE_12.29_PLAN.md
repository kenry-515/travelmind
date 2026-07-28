---
name: phase-12-29-plan
description: Phase 12.29 全面质量加固 — 三线扫描 132 项发现的优先级分类实施计划（2026-07-27）
metadata: 
  node_type: memory
  type: project
  originSessionId: 7b4f2bb5-2f5d-478e-b624-d3334b9a4338
  modified: 2026-07-27T01:17:13.906Z
---

# Phase 12.29 — 全面质量加固

基于三线并行 agent 扫描发现的 132 项优化点，按 **安全 > 测试 > 性能 > 运维 > 代码整洁** 优先级组织为 5 个子阶段。

参考：[[scan-findings-phase12.29]]

---

## Phase 12.29a — 安全 + 配置加固（~2h）

**目标**：消除 HIGH 安全风险，配置生产就绪

| 优先级 | 优化 | 文件 | 说明 |
|--------|------|------|------|
| 🔴 P0 | APP_DEBUG 默认 False | `settings.py` | ✅ 已修复 |
| 🔴 P0 | CORS origins 配置化 | `settings.py` + `main.py` | ✅ 已修复 |
| 🔴 P0 | device_id 格式校验 | `deps.py` | ✅ 已修复（字母数字连字符 1-64 字符） |
| 🔴 P0 | 流式错误脱敏 | `chat.py` | ✅ 已修复（SSE error 不再泄露内部错误） |
| 🔴 P0 | `last_active_at` 更新修复 | `user_service.py` | ✅ 已修复 |
| 🔴 P0 | `_get_user_id` db=None 防护 | `itineraries.py` | 添加 None 检查 |
| 🟡 P1 | 限流信任 X-Forwarded-For 验证 | `rate_limit.py` | 仅在有可信代理时信任 |
| 🟡 P1 | 统一错误格式迁移 | 所有 API 路由 | `HTTPException` → `error_response()` |
| 🟡 P1 | 匿名用户共享目录改进 | `local_itinerary_store.py` | 随机匿名 ID 替代 "anon" |

## Phase 12.29b — 前端质量（~3h）

**目标**：用户体验、性能、可访问性全面改善

| 优先级 | 优化 | 文件 | 说明 |
|--------|------|------|------|
| 🔴 P0 | TypeScript `strict: true` | `tsconfig.app.json` | 开启严格模式 |
| 🔴 P0 | React.lazy 路由分割 | `App.tsx` | 6 页面 lazy load + Suspense |
| 🔴 P0 | ErrorBoundary 启用 | `App.tsx` | 包裹 Routes |
| 🔴 P0 | SSE abort-on-unmount | `ChatPage.tsx` | 组件卸载时取消流 |
| 🟡 P1 | html2canvas/jspdf 动态导入 | `ItineraryPage.tsx` | 减少首屏 ~300KB |
| 🟡 P1 | ImageUploader 键盘可访问 | `ImageUploader.tsx` | role/tabIndex/onKeyDown |
| 🟡 P1 | 骨架屏实际使用 | 各页面 | SkeletonRecommend/SkeletonHistory/SkeletonImage |
| 🟢 P2 | `useCallback`/`useMemo` 优化 | 各页面 | 减少不必要重渲染 |
| 🟢 P2 | 暗色模式 CSS 简化 | `index.css` | 利用 Tailwind dark: 变体 |

## Phase 12.29c — 后端健壮性（~3h）

**目标**：消除并发竞争条件、修复逻辑 bug、完善错误处理

| 优先级 | 优化 | 文件 | 说明 |
|--------|------|------|------|
| 🔴 P0 | `get_llm_provider()` 单例加锁 | `llm_service.py` | asyncio.Lock 防并发创建 |
| 🔴 P0 | `get_session_store()` 单例加锁 | `session_store.py` | 同上 |
| 🔴 P0 | `get_cache()` 单例加锁 | `cache_service.py` | 同上 |
| 🔴 P0 | `get_db` 重复函数清理 | `connection.py` | 保留 deps.py 版，移除 connection.py 版 |
| 🟡 P1 | 数据库索引补全 | `models.py` | user_id FK 列加 index=True |
| 🟡 P1 | 移除 dead code | 多文件 | BAIDU_MAP_AK、重复 import、未使用变量 |
| 🟡 P1 | BUDGET_MAP 集中化 | `core/constants.py` | 三处重复合并为一处 |
| 🟡 P1 | SEASON_MONTHS 集中化 | `core/constants.py` | 三处重复合并为一处 |
| 🟡 P1 | `ownership check` 安全日志 | `itinerary_service.py` | logger.warning 记录所有权失败 |
| 🟢 P2 | 内联 import 移到模块级 | `retriever.py`, `amap_service.py` | import hashlib 移到顶部 |
| 🟢 P2 | 请求体大小限制 | `main.py` | JSON 端点 1MB 限制 |

## Phase 12.29d — 测试体系扩展（~4h）

**目标**：补全 API 层和核心服务的测试覆盖

| 优先级 | 优化 | 文件 | 说明 |
|--------|------|------|------|
| 🔴 P0 | API HTTP 集成测试 | `tests/test_api_*.py` | 每个路由至少 1 个 smoke test |
| 🟡 P1 | weather_service mock 测试 | `tests/test_weather_service.py` | mock httpx |
| 🟡 P1 | llm_service mock 测试 | `tests/test_llm_service.py` | mock AsyncOpenAI |
| 🟡 P1 | orchestrator 管线测试 | `tests/test_orchestrator.py` | 所有 agent mock 的集成测试 |
| 🟢 P2 | trend_agent/vision_agent 单测 | 各 test 文件 | 工具函数覆盖 |

## Phase 12.29e — 运维 + 监控（~2h）

**目标**：Docker 部署生产级、可观测性建立

| 优先级 | 优化 | 文件 | 说明 |
|--------|------|------|------|
| 🔴 P0 | 迁移失败 fail-fast | `docker-entrypoint.sh` | `|| echo` → `|| exit 1` |
| 🔴 P0 | wait-for-DB 重试循环 | `docker-entrypoint.sh` | pg_isready 30 次重试 |
| 🔴 P0 | Docker healthcheck | `docker-compose.yml` | 4 服务各加 healthcheck |
| 🟡 P1 | Prometheus /metrics | `main.py` | prometheus-fastapi-instrumentator |
| 🟡 P1 | 结构化 JSON 日志 | 全局 | python-json-logger + request_id |
| 🟢 P2 | Docker 资源限制 | `docker-compose.yml` | memory/CPU limits |
| 🟢 P2 | 日志轮转配置 | `docker-compose.yml` | max-size/max-file |
| 🟢 P2 | Dependabot 配置 | `.github/dependabot.yml` | pip + npm 自动更新 |

---

## 实施顺序

```
12.29a（安全加固）→ 消除已知风险，立即生效
  ↓
12.29b（前端质量）→ 用户可见改善
  ↓
12.29c（后端健壮性）→ 生产稳定性
  ↓
12.29d（测试扩展）→ 防回退
  ↓
12.29e（运维监控）→ 可观测性
```

每个子阶段：`fixcycle.sh` 验证 → git commit。

**已提前修复（当前会话）**：12.29a 中 5/9 项已完成。

**Why:** 132 项扫描发现表明项目在安全、测试、前端质量三方面有大量低垂果实。优先消除 HIGH 风险，再系统化提升。

**How to apply:** 每个子阶段独立可交付；优先 12.29a（安全）和 12.29b（用户可见）；12.29d（测试）和 12.29e（运维）可以穿插或延后。

---

## ✅ Phase 12.29 全部完成（2026-07-27）

**5 个子阶段已全部实施完毕：**

| 子阶段 | 状态 |
|--------|------|
| 12.29a 安全 + 配置加固 | ✅ 已修复 |
| 12.29b 前端质量 | ✅ 已修复 |
| 12.29c 后端健壮性 | ✅ 已修复 |
| 12.29d 测试体系扩展 | ✅ 已修复（+24 测试 → 373 全过） |
| 12.29e 运维 + 监控 | ✅ 已修复 |

详见  §9 变更记录。
