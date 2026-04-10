# HydroAgent 测试说明

本文档记录当前测试状态和后续重建计划。项目已经从早期 CLI / Gradio / 单模块结构演进为 FastAPI + 服务层 + Next.js 控制台架构，因此早期测试不再适合作为最终验收依据。

## 当前结论

- 前端质量门槛可作为当前有效验收项：
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`
- 后端 `tests/` 中保留了历史测试和部分新架构测试。
- 旧测试中存在导入路径、缺失历史依赖、直接启动真实服务等问题。
- 后端最终验收应围绕当前主链路重建：登录、权限、分区状态、计划生成、审批、拒绝、执行、灌溉日志、告警、审计和报表。

## 旧测试问题

已知不适合作为最终验收的点：

- `tests/test_main.py` 直接调用 `src.main.main()`，会启动真实 Uvicorn 服务并阻塞测试进程。
- 早期 `src/ui/ui.py` 依赖 Gradio，但当前主前端已经迁移到 Next.js。
- 早期 `src/llm/llm_agent.py` 依赖 `run_agent` 兼容入口，但当前主智能体入口在 `src/llm/langchain_agent.py`。
- 早期天气工具测试依赖 `langchain_community`，但当前主链路不应依赖旧天气工具作为验收入口。
- 部分日志测试仍按旧 logger 行为断言，与当前配置化日志级别不一致。

## 建议测试重建范围

### 后端集成测试

- 登录成功和失败。
- RBAC 权限拦截。
- 获取分区列表和分区状态。
- 低湿度、无降雨时生成 `start` 计划。
- 有降雨且非紧急湿度时生成 `hold` 计划。
- 缺失传感器数据时生成阻断或暂缓计划。
- 批准计划后可执行。
- 拒绝计划不可执行。
- 执行计划后写入 `PlanExecutionEvent` 和 `IrrigationLog`。
- 告警生成、确认、解决。
- 审计事件写入。
- 报表导出接口返回 CSV。

### 前端验证

- 登录页能正常登录。
- 运营总览能加载分区、天气和灌溉状态。
- 运营中心能审批和执行计划。
- 智能对话页能创建会话并接收 SSE。
- 设置页能保存模型和策略配置，并且密钥不明文回显。

## 建议命令

前端：

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

后端重建完成后建议提供统一入口：

```bash
. .venv/bin/activate
python -m unittest discover -s tests
```

在旧测试尚未重建前，不建议把 `python -m unittest discover -s tests` 的结果写入论文最终测试结论。

## 论文表述建议

可以写：

```text
系统完成后对前端类型检查、静态检查和生产构建进行了验证；后端主业务链路通过接口级调试和局部集成测试验证。由于系统架构从早期原型重构为 FastAPI + Next.js 结构，历史测试用例需要按新架构重新整理，最终验收以当前服务层主链路为准。
```
