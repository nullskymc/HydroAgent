# HydroAgent — 水利灌溉智能体系统

HydroAgent（原 SmartIrrigation）是一个面向毕业设计与原型验证场景的智能灌溉决策平台。系统以 FastAPI 后端为核心，结合 SQLAlchemy 数据模型、分区化灌溉计划、审批与执行链路、RBAC 权限、告警、审计、报表、知识库和 LLM 智能对话，并提供基于 Next.js 的现代化运营控制台。

当前项目定位是“智能灌溉仿真与决策原型系统”：传感器采集、部分执行器控制和 ML 预测默认使用仿真实现，便于在没有真实硬件的毕业设计环境中完成完整业务演示。真实硬件接入可以在现有数据采集、执行器服务和控制接口基础上替换适配层。

## 核心能力

- **分区化灌溉决策**：按农田分区维护传感器、执行器、作物阈值和默认灌溉时长。
- **结构化计划闭环**：计划包含证据、风险等级、安全审查、建议动作和建议时长；启动灌溉必须经过计划与审批链路。
- **审批与执行审计**：支持计划生成、批准、拒绝、执行、手动覆盖、执行日志和后台审计记录。
- **安全策略约束**：传感器缺失、执行器不可用、未来 48 小时降雨等情况会进入暂缓或高风险路径，避免自动执行。
- **数据与天气处理**：支持传感器数据清洗、天气查询、天气风险摘要和离线兜底数据。
- **AI 对话与工具调用**：通过 LLM 智能体、MCP 工具和持久化会话支持自然语言查询、计划生成和过程追踪。
- **后台管理能力**：包含 RBAC 权限、用户角色、资产管理、告警处理、知识库、报表导出、系统设置和模型配置。
- **Next.js 运营控制台**：提供总览、对话、运营、资产、知识库、告警、用户、报表、历史和设置页面。

## 技术栈

- 后端：Python 3.12 推荐、FastAPI、SQLAlchemy、SQLite / PostgreSQL / MySQL、LangChain、FastMCP、OpenAI SDK。
- 前端：Next.js、React、TypeScript、ECharts、ESLint。
- 存储：业务数据使用 SQLAlchemy；对话与工具轨迹使用 LangGraph SQLite persistence；知识库支持 Chroma 向量存储。
- 部署：本地脚本、Dockerfile、docker-compose、GitHub Actions 镜像构建工作流。

## 目录结构

- `src/`：后端服务源码。
  - `main.py`：FastAPI 应用入口。
  - `api.py`：核心 API，包括对话、分区、计划、灌溉、设置、状态等。
  - `database/`：SQLAlchemy 数据模型与数据库初始化。
  - `services/`：业务服务层，包括灌溉计划、资产、告警、RBAC、认证、报表、分析。
  - `data/`：传感器采集与天气数据处理。
  - `llm/`：智能体、工具参数解析、对话持久化和中间件。
  - `knowledge/`：知识库文档与检索服务。
  - `ml/`：土壤湿度预测模型接口，当前默认仿真实现。
  - `control/`、`ui/`：早期兼容模块，当前主流程以 `services/irrigation_service.py` 和 Next.js 前端为准。
- `frontend/`：Next.js 前端控制台与 API 代理路由。
- `tests/`：历史测试与部分新架构测试。由于架构已经大改，旧测试需要重新梳理后再作为最终验收依据。
- `docs/`：毕业设计、部署、天气、架构和演示说明。
- `config.template.yaml`：配置模板。实际 `config.yaml` 可能包含本地密钥，不应提交到仓库。

## 快速开始

### 一键本地启动

```bash
./start.sh
```

默认后端地址为 `http://127.0.0.1:7860`，前端地址为 `http://127.0.0.1:3000`。

### 分别启动后端和前端

```bash
./start-backend.sh
```

```bash
./start-frontend.sh
```

### 手动启动

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

```bash
cd frontend
npm install
npm run dev
```

### 默认演示账号

系统启动后会自动写入默认用户，便于毕业设计演示：

- 管理员：`admin / admin123`
- 运营经理：`manager / manager123`
- 值班操作员：`operator / operator123`
- 只读观察员：`viewer / viewer123`
- 审计员：`auditor / auditor123`

## 毕设说明

建议答辩时将本项目表述为“面向农业灌溉场景的智能决策与安全执行原型系统”。当前重点不是直接驱动真实水泵，而是证明系统已经具备数据采集、天气风险、分区建模、计划生成、人工审批、执行记录、告警审计和可视化运营的完整软件链路。

关键文档：

- [系统架构说明](./docs/architecture.md)
- [答辩演示脚本](./docs/demo_script.md)
- [开发任务清单](./docs/task.md)
- [Docker 部署说明](./docs/docker_guide.md)
- [天气模块说明](./docs/README_weather.md)

## 质量检查

前端当前可执行：

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

后端历史测试位于 `tests/`。由于系统从早期 CLI / Gradio / 单模块结构演进为 FastAPI + Next.js + 服务层架构，旧测试中存在导入路径、依赖和启动方式不匹配的问题，后续应按当前业务主链路重建测试用例。
