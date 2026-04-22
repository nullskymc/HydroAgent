# HydroAgent Docker 部署指南

本文档说明当前 Docker 相关文件的用途。项目已经演进为“FastAPI 后端 + Next.js 前端”双服务结构；生产环境建议使用 `docker-compose.yml` 一次启动后端和前端两个服务。

## 系统要求

- Docker 20.10.0 或更高版本。
- Docker Compose 2.0.0 或更高版本。
- 如需本地开发前端，请安装 Node.js 和 npm；生产 compose 会在容器内构建前端。

## 生产 Compose 运行

```bash
docker-compose up --build
```

默认服务地址：

```text
前端：http://localhost:3000
后端：http://localhost:7860
```

健康检查：

```text
http://localhost:7860/api/health
```

API 文档：

```text
http://localhost:7860/api/docs
```

## 服务结构

`docker-compose.yml` 包含两个服务：

- `backend`：FastAPI 后端，使用仓库根目录 `Dockerfile` 构建，端口 `7860`。
- `frontend`：Next.js 前端，使用 `frontend/Dockerfile` 构建，端口 `3000`，通过 `BACKEND_API_BASE_URL=http://backend:7860` 访问后端。

## 前端本地生产运行

如果不使用 Docker，也可以在 Node.js 环境中运行前端生产构建：

```bash
cd frontend
npm ci
BACKEND_API_BASE_URL=http://127.0.0.1:7860 npm run build
BACKEND_API_BASE_URL=http://127.0.0.1:7860 npm run start
```

本地开发仍然可以使用：

```bash
cd frontend
BACKEND_API_BASE_URL=http://127.0.0.1:7860 npm run dev
```

## 配置说明

`docker-compose.yml` 主要配置：

- 后端端口映射：`7860:7860`
- 前端端口映射：`3000:3000`
- 后端日志挂载：`./logs:/app/logs`
- 后端配置挂载：`./config.yaml:/app/config.yaml:ro`
- 前端后端地址：`BACKEND_API_BASE_URL=http://backend:7860`
- 本地 HTTP 登录：`AUTH_COOKIE_SECURE=false`
- 时区：`Asia/Shanghai`

如需使用本地构建镜像，可以将 compose 文件改为：

```yaml
services:
  backend:
    build: .
    ports:
      - "7860:7860"
    volumes:
      - ./logs:/app/logs
      - ./config.yaml:/app/config.yaml
```

## 环境变量建议

生产环境至少应配置：

- `HYDROAUTH_SECRET`：后端访问令牌签名密钥。
- `HYDRO_CONFIG_SECRET`：配置密钥加密密钥。
- `OPENAI_API_KEY`：LLM 服务密钥，如使用设置页加密保存也可以不直接写入环境变量。
- `FRONTEND_ORIGINS`：允许访问后端的前端地址，例如 `https://your-frontend.example.com`。
- `BACKEND_API_BASE_URL`：前端服务访问后端的地址；compose 内部默认为 `http://backend:7860`。
- `AUTH_COOKIE_SECURE`：使用 HTTPS 时设为 `true`；本地 HTTP compose 验证时可以保留 `false`。
- `DB_TYPE`、`DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`：如使用外部数据库。

## 故障排除

- 容器无法启动：运行 `docker-compose logs` 查看后端日志。
- 健康检查失败：确认 `http://localhost:7860/api/health` 是否返回 `{"status":"ok"}`。
- 前端无法访问后端：确认 `BACKEND_API_BASE_URL` 指向后端地址，并确认后端 `FRONTEND_ORIGINS` 包含前端来源。
- 配置没有生效：确认 `config.yaml` 已挂载到 `/app/config.yaml`，且容器重启后重新读取。
- 数据重置：当前 compose 不挂载 SQLite 数据库；容器删除或重建后会重新初始化演示数据。

## 后续完善

如果需要完整生产部署，建议补充：

- 反向代理与 HTTPS 配置。
- 数据库迁移方案。
- 日志采集与监控。
- CI 中的后端测试、前端 typecheck、lint 和 build。
