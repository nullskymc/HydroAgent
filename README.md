# HydroAgent — 水利灌溉智能体

HydroAgent（原名 SmartIrrigation）是一个面向现代农业的智能化灌溉决策与控制系统。集成了数据采集与处理、机器学习分析、LLM 智能脑决策、自动控制和报警等模块。并且拥有基于 React 和 Vite 构建的、全新 Vercel 极简设计风格的现代前端监控终端，旨在将前沿的人工智能技术与实际农业生产深度结合。

## 主要特性

- **配置管理**：支持多环境配置，灵活集成数据库、API、传感器等参数。
- **数据采集与处理**：自动采集土壤、气象等多维度数据，内置数据清洗与异常检测。
- **数据库支持**：基于 SQLAlchemy，支持主流数据库，结构化存储传感器、天气、灌溉日志等信息。
- **机器学习预测**：可集成 LSTM 等模型，预测土壤湿度趋势，辅助决策。
- **智能体决策**：LLM 智能体解析自然语言指令，自动决策灌溉与报警。
- **自动控制与报警**：支持软/硬件灌溉设备控制，阈值报警，支持邮件/短信等扩展。
- **现代可视化前台**：基于 React 18 + Vite 开发，应用完整的 Vercel 极简设计系统，提供深色模式响应式监控大屏与 Agent 交互端。
- **模块化设计**：各功能高度解耦，便于扩展和维护。
- **完善测试**：覆盖核心功能的单元与集成测试。

## 目录结构

- `src/`  主程序源码
  - `config/` 配置管理
  - `database/` 数据库模型与操作
  - `exceptions/` 异常定义
  - `data/` 数据采集与处理
  - `ml/` 机器学习模型
  - `llm/` 智能体
  - `control/` 控制执行
  - `alarm/` 报警模块
  - `ui/` 用户界面
  - `main.py` 主入口
  - `logger_config.py` 日志配置
- `tests/`  测试用例
- `requirements.txt` 后端依赖资源
- `frontend/` React 现代前端根目录
- `task.md` 详细开发任务清单

## 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 配置数据库和环境变量（可选 .env 或 config.yaml）
   - 请勿上传包含敏感信息的 config.yaml 到仓库，参考 `config.template.yaml` 创建你的配置文件。
   - `config.template.yaml` 支持 `model_name` 字段用于 LangChain 智能体模型选择，例如：
     ```yaml
     model_name: gpt-4o  # 可选 gpt-4, gpt-3.5-turbo 等
     ```
3. 启动前端终端：
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
4. 初始化数据库并启动核心调度中心：`python src/main.py --init-db`
5. 日常启动后端：`python src/main.py`

## 适用场景

- 农田、温室、园艺等需智能灌溉的场景
- 需要数据驱动决策和远程监控的农业项目

## 贡献与反馈

欢迎提交 Issue、PR 或建议！

---

详细开发任务与模块说明请见 [task.md](./task.md)
