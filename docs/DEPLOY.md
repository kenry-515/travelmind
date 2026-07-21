# TravelMind Agent — Docker 部署指南

> 适用环境：Docker Desktop（Windows/Mac/Linux），Docker Compose v2+。
> 本文档步骤可从零复现：任何人 clone 仓库后按序执行即可跑起完整系统。

## 1. 前置准备

```bash
git clone <repo-url> && cd TravelMindAgent

# 必填：复制环境模板并填入真实 Keys
cp backend/.env.example backend/.env
# 编辑 backend/.env，至少填：
#   DEEPSEEK_API_KEY   — DeepSeek 主 LLM（对话/规划）
#   MOONSHOT_API_KEY   — Kimi 开放平台（图片识别）
#   AMAP_API_KEY + AMAP_SIGN_KEY — 高德 POI/路线
# 其余保持默认即可（compose 会覆盖 SESSION_STORE/REDIS_URL/DATABASE_URL）
```

## 2. 启动

```bash
docker compose up --build -d
```

- 首次构建约 5-15 分钟（后端 pip、前端 npm）
- 后端首次启动时若向量库为空，entrypoint 会自动从 `backend/data/attractions.json`
  重建 TF-IDF + Chroma（约 10-30 秒，日志可见 `Chroma 向量库为空，开始重建`）
- 可选 PostgreSQL：`docker compose --profile db up -d`（默认不启用，系统降级运行无碍）

## 3. 验证

```bash
curl http://localhost:8000/api/v1/health
# 期望：{"status":"degraded" 或 "ok"，services.api="healthy"}
# （未启用 postgres 时 database=unavailable 属正常降级）

# 浏览器打开前端
http://localhost:5173
```

完整链路：首页「检测后端连接」→「AI 对话」聊到生成行程卡片 →
行程页可见「真实数据校验」卡片（POI 存续/顺路/天气）。

## 4. 常用命令

```bash
docker compose logs -f backend      # 看后端日志（含 RAG/管线/校验）
docker compose restart backend      # 重启后端（会话不丢：Redis 外置）
docker compose down                 # 停止并移除容器（数据卷保留）
docker compose down -v              # 停止并删除数据卷（Chroma/Redis/PG 全清，慎用）
docker compose up --build -d backend  # 只重建后端（改代码后）
```

## 5. 数据与持久化

| 数据 | 位置 | 说明 |
|---|---|---|
| Chroma 向量库 | 命名卷 `chroma-data` | 首次自举后持久化，重启不重建 |
| 对话会话 | Redis 卷 `redis-data` | TTL 2h，重启后端不丢 |
| 知识库 | `./backend/data`（只读挂载） | 更新数据后 `restart backend` 生效 |
| PostgreSQL | 卷 `pg-data`（--profile db） | 可选组件 |

## 6. 排错清单

| 症状 | 排查 |
|---|---|
| 后端反复重启 | `docker compose logs backend`；常见是 `.env` 缺 Key 或格式错（pydantic extra=forbid） |
| 构建 pip 超时/慢 | 国内网络可在 `backend/Dockerfile` 的 pip 命令加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| npm ci 慢 | 同上，前端构建期可配 npm 镜像源 |
| recommend 返回空 | 向量库没建起来：看日志是否有「开始重建」；手动 `docker compose exec backend python scripts/build_knowledge_base.py` |
| 会话重启丢失 | 确认 `SESSION_STORE=redis`（compose 已强制）且 redis 容器健康 |
| 5173 白页 | 前端 nginx 反代未通：`docker compose ps` 确认 backend 在跑；`curl localhost:8000/api/v1/health` |
| GitHub 拉不动镜像（国内） | 给 Docker Desktop 配镜像加速器，或开代理 |

## 7. 与非 Docker 方式的关系

Docker 部署与本地直跑（`uvicorn` + `npm run dev`）完全等价：
同一套代码、同一套 `.env` 语义。CI/冒烟/契约回归脚本在两种模式下通用
（只要 `:8000` 有健康后端即可）。
