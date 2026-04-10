---
id: approval-execution
name: 审批与执行
description: 面向计划审批、拒绝和执行的技能，强调审批边界、执行条件和回执追踪。
trigger_hints:
  - 批准计划
  - 拒绝计划
  - 执行计划
  - approve
  - execute
mode_allowlist:
  - operator
tool_allowlist:
  - list_farm_context
  - list_farm_zones
  - get_zone_operating_status
  - get_plan_status
  - approve_irrigation_plan
  - reject_irrigation_plan
  - execute_approved_plan
  - control_irrigation
  - search_knowledge_base
resources:
  - hydro://irrigation/status
workflow:
  get_plan_status: planning
  approve_irrigation_plan: approval
  reject_irrigation_plan: approval
  execute_approved_plan: execution
  control_irrigation: execution
instruction_append: |
  当本技能激活时，严格先读取计划状态，再执行审批或执行动作。
  对未批准计划，必须停在审批边界并明确说明不能执行的原因。
---
本技能只服务已存在计划的审批和执行，不负责绕过结构化计划流程。
