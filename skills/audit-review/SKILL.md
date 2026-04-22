---
id: audit-review
name: 审计追踪
description: 面向历史回放、风险解释和决策溯源的技能，强调 trace、decision、plan 的因果链。
trigger_hints:
  - 审计
  - 追踪
  - 为什么
  - risk
  - audit
mode_allowlist:
  - advisor
  - auditor
  - operator
tool_allowlist:
  - list_farm_context
  - list_farm_zones
  - query_sensor_data
  - query_weather
  - get_zone_operating_status
  - get_plan_status
  - statistical_analysis
  - anomaly_detection
  - time_series_forecast
  - correlation_analysis
  - search_knowledge_base
resources:
  - hydro://zones
  - hydro://irrigation/status
  - hydro://alarm/status
workflow:
  query_sensor_data: evidence
  query_weather: evidence
  anomaly_detection: analysis
  statistical_analysis: analysis
  get_plan_status: audit
instruction_append: |
  当本技能激活时，优先解释“为什么系统得出这个结论”，并把证据、风险、计划状态和审批状态串起来。
---
本技能用于复盘和解释，不应主动生成新计划或执行新动作。
