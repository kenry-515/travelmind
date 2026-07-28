# TravelMind Agent — SOP 矩阵

> 最后更新：2026-07-28
> 本文件记录每个功能的正向/逆向路径、API 行为边界、环境问题排查方法。
> **新增功能/端点时必须同步更新此文件。**

---

## 目录

1. [页面 SOP 矩阵](#1-页面-sop-矩阵)
2. [API SOP 矩阵](#2-api-sop-矩阵)
3. [对话状态机 SOP](#3-对话状态机-sop)
4. [环境问题 SOP](#4-环境问题-sop)
5. [质量基线](#5-质量基线)

---

## 1. 页面 SOP 矩阵

### 1.1 首页（`/` — HomePage）

| 操作 | 正向路径 | 逆向路径 1 | 逆向路径 2 | 逆向路径 3 |
|------|---------|-----------|-----------|-----------|
| 页面加载 | 渲染 hero + 搜索栏 + 4 个快捷导航卡片 + 示例问题 | —（纯静态页） | — | — |
| 输入查询 → 回车 | 导航到 `/chat?q=...` | 空输入 → 前端阻止 | — | — |
| 点击示例问题 | 导航到 `/chat?q=...` | — | — | — |
| 点击快捷导航 | 导航到目标页面 | 目标页面崩溃 → ErrorBoundary + 「返回首页」 | — | — |
| 暗色模式切换 | `.dark` 类添加到 `<html>` + localStorage 持久化 | — | — | — |
| Ctrl+K 快捷键 | 导航到 `/chat` | — | — | — |

### 1.2 推荐页（`/recommend` — RecommendPage）

| 操作 | 正向路径 | 逆向路径 1 | 逆向路径 2 | 逆向路径 3 |
|------|---------|-----------|-----------|-----------|
| 页面加载 | 显示搜索栏 + 4 个快捷 chip + 空状态提示 | — | — | — |
| 输入城市 → 搜索 | `POST /recommend` → 骨架屏 → PlaceCard 列表 | 空输入 → 按钮 disabled | API 502/500 → AlertCircle + 错误消息 + 「重新搜索」 | 0 结果 → 空结果提示 |
| 点击快捷 chip | 自动填充 + 开始搜索 | — | — | — |
| 点击「生成行程」 | 导航到 `/itinerary?q=...` | 多城市结果 → 按钮隐藏 + 琥珀色提示 | — | — |
| 暗色模式 | `.dark` → 卡片/背景/文字颜色变化 | — | — | — |

### 1.3 对话式规划（`/chat` — ChatPage）

| 操作 | 正向路径 | 逆向路径 1 | 逆向路径 2 | 逆向路径 3 |
|------|---------|-----------|-----------|-----------|
| 页面加载（有 `?q=`） | 自动发送 query 到 dialog/message | — | — | — |
| 输入消息 → 回车 | `POST /dialog/message` → 回复渲染 + 槽位更新 | 空消息 → 后端返回「我在听」提示 | API 500 → Toast 错误 | 网络断连 → 错误提示 |
| 填满槽位 | 进入 `confirming` 阶段 → 显示摘要 + 「生成行程卡片」按钮 | 城市无覆盖 → `refused` + 替代城市建议 | — | — |
| 点击「生成行程卡片」 | `POST /dialog/generate/stream` → SSE 6 步进度 → 行程卡片 | 生成失败 → 回到 `confirming` | SSE 断开 → 自动 fallback 到 blocking API | — |
| 修改已生成行程 | `delivered` 阶段 → 输入修改意见 → `regenerate_day` / 整体重来 | 要删的 POI 是当天唯一 → 提示无法删除 | — | — |
| 暗色模式 | `.dark` → header/intentBar/消息气泡颜色变化 | — | — | — |

### 1.4 行程页（`/itinerary` — ItineraryPage）

| 操作 | 正向路径 | 逆向路径 1 | 逆向路径 2 | 逆向路径 3 |
|------|---------|-----------|-----------|-----------|
| 页面加载（`?q=`） | SSE 管线 → 6 步进度 → 完整行程渲染 | 管线出错 → 错误视图 + 重试 + 返回推荐 | — | — |
| 页面加载（`?id=`） | `GET /itineraries/{id}` → 行程渲染 | ID 无效 → 错误提示 | API 500 → 错误提示 | DB 不可用 → 空状态 |
| 页面加载（sessionStorage） | 读取缓存行程 → 渲染 | 无数据 → 空状态 CTA（去对话/推荐） | JSON 损坏 → 优雅降级到空状态 | — |
| 单项删除 | 本地移除 → 重算地点数 → 写回 sessionStorage | 当天只剩 1 项 → Toast「不能删」 | — | — |
| 单项重排 | `POST /agent/plan/regenerate-day` → 更新当天 | 重排失败 → Toast 错误 | — | — |
| PDF 导出 | 动态导入 html2canvas+jspdf → 生成 PDF | 导出失败 → Toast 错误 | — | — |
| 收藏 | `POST /favorites` → 心形变红 | 重复收藏 → 提示已收藏 | API 500 → Toast 错误 | — |
| 暗色模式 | `.dark` → 所有区块/卡片颜色变化 | — | — | — |

### 1.5 识图页（`/image` — ImagePage）

| 操作 | 正向路径 | 逆向路径 1 | 逆向路径 2 | 逆向路径 3 |
|------|---------|-----------|-----------|-----------|
| 页面加载 | 显示 ImageUploader idle 状态 + 使用提示 | — | — | — |
| 选择图片 → 识别 | `POST /image/analyze` → 分析结果 + 自动相似地点搜索 | 非图片格式 → Toast 格式错误 | 图片 >10MB → Toast 太大 | 超时 → 「换小图」提示 |
| 识别成功 | 展示 location/confidence/landmark_features/tags | — | — | — |
| 相似地点 | `POST /recommend/by-tags` → PlaceCard 网格 | API 500 → 错误条 | 无结果 → 空状态 | — |
| 暗色模式 | `.dark` → 上传区/结果卡片颜色变化 | — | — | — |

### 1.6 历史页（`/history` — HistoryPage）

| 操作 | 正向路径 | 逆向路径 1 | 逆向路径 2 | 逆向路径 3 |
|------|---------|-----------|-----------|-----------|
| 页面加载 | `GET /itineraries` + `GET /favorites` → 平行请求 → 列表渲染 | 无行程 → 空状态 + 「去规划」CTA | API 500 → 错误提示 + 重试 | DB 不可用 → 空列表 |
| 点击行程项 | `GET /itineraries/{id}` → 导航到 `/itinerary?id=...` | 加载失败 → 错误 Toast | — | — |
| 删除行程 | `DELETE /itineraries/{id}` → 乐观移除 | API 500 → Toast 删除失败 | 已无权限 → Toast 提示 | — |
| 暗色模式 | `.dark` → 列表/卡片颜色变化 | — | — | — |

---

## 2. API SOP 矩阵

### 2.1 健康检查

| 端点 | 方法 | 正向响应 | 错误响应 | 降级行为 |
|------|------|---------|---------|---------|
| `/api/v1/health` | GET | `200 {"status":"ok","services":{"api":"healthy","database":"healthy"}}` | 503 → 全局不可用 | DB 不可用时 status=degraded, database=unavailable |

### 2.2 聊天

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `/api/v1/chat` | POST | 200 `{content, session_id, model}` | 422 空消息 / 超长消息 | 502 UPSTREAM_ERROR | — |

### 2.3 Agent 规划

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `/api/v1/agent/plan` | POST | 200 `PlanResponse{profile,recommendations,itinerary,weather}` | 422 空输入 | 502 UPSTREAM_ERROR | 每步 catch 异常→state.error |
| `/api/v1/agent/plan/stream` | POST | SSE: progress→result→saved 事件 | 422 空输入 | SSE error 事件 | 同上 |
| `/api/v1/agent/profile` | POST | 200 `ProfileResponse{destination,days,tags,...}` | 422 空输入 | 502 UPSTREAM_ERROR | — |
| `/api/v1/agent/plan/regenerate-day` | POST | 200 `{itinerary}` | 400 越界 day_index | 502 UPSTREAM_ERROR | 重试 3 次后失败 |

### 2.4 推荐

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `/api/v1/recommend` | POST | 200 `RecommendResponse{city,places[],trend_summary}` | 422 空输入 | 502 UPSTREAM_ERROR | 多城市自动模式、无覆盖城市→空结果 |
| `/api/v1/recommend/quick` | POST | 200 `QuickRecommendResponse{city,places[]}` | 422 缺 city | — | 同上 |
| `/api/v1/recommend/by-tags` | POST | 200 `ByTagsResponse{places[],cities_covered[]}` | 422 空 tags | — | 同上 |

### 2.5 天气

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `/api/v1/weather/cities` | GET | 200 `{cities:[...]}` | — | — | 从 KB 加载城市列表 |
| `/api/v1/weather/{city}` | GET | 200 `WeatherForecast{daily[],advice}` | 404 不支持的城市 | 502 Open-Meteo 不可用 | L1+L2 缓存降级 |
| `/api/v1/weather/travel-advice` | POST | 200 `{advice}` | 422 无效参数 | 502 | — |

### 2.6 图片分析

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `/api/v1/image/analyze` | POST | 200 `ImageAnalyzeResult{location,tags[],confidence}` | 400 无图片/格式错, 413 超大文件 | 502 UPSTREAM_ERROR / 超时 | Kimi 不可用→502 返回 |

### 2.7 对话

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `/api/v1/dialog/message` | POST | 200 `DialogResponse{reply,stage,slots,itinerary?}` | 422 解析错误 | 502 UPSTREAM_ERROR | DB 不可用→memory session |
| `/api/v1/dialog/generate` | POST | 200 `DialogResponse{itinerary,itinerary_id?}` | 422 无 session | 502 生成失败回复到 confirming | SSE 不可用→ blocking fallback |
| `/api/v1/dialog/generate/stream` | POST | SSE: progress→result→saved | 422 无 session | SSE error 事件 | 同上 |

### 2.8 行程 CRUD

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `GET /api/v1/itineraries` | GET | 200 `{itineraries[],total,page}` | — | 500 → 空列表 | DB 不可用→空列表 |
| `GET /api/v1/itineraries/{id}` | GET | 200 `ItineraryDetailResponse` | 404 不存在 | 500 → 错误 | DB 不可用→local store |
| `DELETE /api/v1/itineraries/{id}` | DELETE | 204 | 403 非主人 / 404 不存在 | 500 → 错误 | — |
| `GET .../versions` | GET | 200 `{versions[]}` | 404 行程不存在 | 500 → 空列表 | DB 不可用→空 |
| `POST .../restore/{vid}` | POST | 200 `{itinerary,version}` | 404 版本不存在 | 500 | — |

### 2.9 收藏

| 端点 | 方法 | 正向响应 | 400 错误 | 500 错误 | 降级行为 |
|------|------|---------|---------|---------|---------|
| `GET /api/v1/favorites` | GET | 200 `{favorites[]}` | — | 500 → 空列表 | DB 不可用→空 |
| `POST /api/v1/favorites` | POST | 200 `{ok:true,favorite?}` | 400 无效 target_type | 500 → 错误 | DB 不可用→失败 |
| `DELETE /api/v1/favorites/{id}` | DELETE | 204 | 403 非主人 / 404 | 500 → 错误 | — |

---

## 3. 对话状态机 SOP

### 3.1 状态转换

```
collecting ──(槽位全满)──→ confirming ──(确认)──→ generating ──(生成完成)──→ delivered
    │                         │                                                  │
    │(城市不支持)              │(修改)                                            │(修改)
    ↓                         ↓                                                  ↓
  refused                  confirming ──(global/slot_change)                  delivered
                                 │                                              (本地删除/单天重排)
                                 └──(local)──→ regenerating
```

### 3.2 各阶段行为

| 阶段 | 入口 | 可执行操作 | 超时/异常 |
|------|------|-----------|----------|
| **collecting** | 首次发送消息 | 自由文本 / slot_override 直接填槽 | 无超时 |
| **confirming** | 槽位收敛完成 | 确认生成 / 手动改槽位 | — |
| **generating** | 点击「生成行程卡片」 | 等待 SSE 完成 / 输入排队 | 120s 超时→回到 confirming |
| **delivered** | 生成完成 | 修改(本地/单天/全局) / 收藏 / 导出 | — |
| **refused** | 城市不支持 | 选择替代城市 | 终端状态 |

### 3.3 修改分类

| 修改类型 | 触发词 | 行为 | 技术实现 |
|---------|--------|------|---------|
| 本地删除 | "去掉/删除/不去/不想去 + POI名" | 移除当天 item（≥1 保留） | 正则匹配 + 本地数组操作 |
| 单天重排 (local) | "第二天太赶" / "第N天改一下" | `regenerate_day()` 替换当天 | POST /agent/plan/regenerate-day |
| 槽位修改 (slot_change) | "改成3天" / "预算提高" | 覆盖槽位→回到 confirming | slot_override |
| 全局重来 (global) | "整体重新规划" | 回到 confirming state | slot_override |
| 未知 (unknown) | 无法匹配以上 | LLM 分类 fallback | `_classify_with_llm()` |

---

## 4. 环境问题 SOP

### 4.1 端口 8000 被占用

| 项目 | 内容 |
|------|------|
| **症状** | `Errno 10048` / `Address already in use` |
| **诊断** | `netstat -ano \| findstr :8000` 或 `preflight_check.py` |
| **常见原因** | 另一个项目 Docker 容器映射了 8000（如 `my-agent-demo-agent`）|
| **修复** | `docker stop <container>` + 重启 TravelMind 后端 |
| **预防** | preflight_check.py 在 fixcycle 中自动运行 |

### 4.2 后端跑错项目

| 项目 | 内容 |
|------|------|
| **症状** | `/api/v1/recommend` 404 / 路由只有 `/health`, `/chat` 等少数 |
| **诊断** | `curl localhost:8000/openapi.json \| python -c "import json,sys; print(len(json.load(sys.stdin)['paths']))"` |
| **常见原因** | 先启动的其他 uvicorn 项目占用了 8000 端口 |
| **修复** | 杀掉错误进程 + 启动正确后端 |
| **预防** | preflight 的路由数和前缀校验 |

### 4.3 API Key 缺失

| 项目 | 内容 |
|------|------|
| **症状** | DeepSeek: `DEEPSEEK_API_KEY is not set`, Kimi: 502 UPSTREAM_ERROR |
| **诊断** | preflight_check.py → ENV_KEYS 检查 |
| **常见原因** | `.env` 未复制或 Key 过期 |
| **修复** | `cp .env.example .env` + 填入真实 Key |
| **预防** | preflight_check.py 检测缺失 Key |

### 4.4 数据库不可用

| 项目 | 内容 |
|------|------|
| **症状** | 行程/历史/收藏功能不可用，/api/v1/health 显示 database=unavailable |
| **诊断** | `docker compose ps` → postgres 是否运行 |
| **常见原因** | PostgreSQL 容器未启动 / 端口冲突 / 配置错误 |
| **修复** | `docker compose up -d postgres` 或 `docker compose --profile db up -d` |
| **降级** | 行程使用 local_itinerary_store（JSON 文件），收藏和历史返回空列表 |

### 4.5 暗色模式视觉异常

| 项目 | 内容 |
|------|------|
| **症状** | 功能页面顶部 header 白色 |
| **诊断** | 检查 `.glass` 类是否有 `dark .glass` 覆写 |
| **常见原因** | `.glass` 硬编码 `rgb(255 255 255 / 0.8)` 缺少 dark mode 覆写 |
| **修复** | `index.css` 中加 `.dark .glass { background-color: rgb(30 41 59 / 0.8); }` |
| **预防** | E2E `theme.spec.ts` 检查每个页面的 `.glass` 颜色 |

---

## 5. 质量基线

### 5.1 评测指标

| 指标 | Phase 12.28 | Phase 12.29 | 说明 |
|------|------------|------------|------|
| **Micro** | 83.7% | ⏳ 评测中 | 约束单元格通过率 |
| **Macro** | 61.3% | ⏳ 评测中 | query 全约束通过率 |
| **测试数** | 349 | 483 | pytest 单元测试 |
| **POI 数** | 2,321 | 2,410 | KB 景点 |
| **城市数** | 30 | 30 | 覆盖城市 |

### 5.2 E2E 测试

| 套件 | 状态 | 说明 |
|------|------|------|
| Playwright E2E | ⏳ 实施中 | 8 个 spec 覆盖 6 页面 + 暗色模式 + 导航 |

### 5.3 环境预检

| 检查项 | 状态 | 说明 |
|--------|------|------|
| preflight_check.py | ✅ 已实现 | 7 项检查，集成到 fixcycle |

---

> **维护要点**：
> - 新增 API 端点 → 更新 §2 API SOP 矩阵
> - 新增页面 → 更新 §1 页面 SOP 矩阵
> - 新增降级路径 → 更新所有相关矩阵
> - 修改对话状态机 → 更新 §3
> - 发现新的环境问题 → 更新 §4
> - 跑完评测 → 更新 §5.1
