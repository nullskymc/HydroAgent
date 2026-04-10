---
id: plan-generation
name: 灌溉计划生成
description: 面向分区灌溉计划生成的技能，强调证据收集、风险说明和结构化计划输出。
trigger_hints:
  - 生成灌溉计划
  - 计划
  - irrigation plan
  - 建议灌溉
mode_allowlist:
  - planner
  - operator
tool_allowlist:
  - list_farm_context
  - list_farm_zones
  - query_sensor_data
  - query_weather
  - get_zone_operating_status
  - recommend_irrigation_plan
  - predict_soil_moisture
  - create_irrigation_plan
  - get_plan_status
  - search_knowledge_base
resources:
  - hydro://zones
  - hydro://irrigation/status
workflow:
  query_sensor_data: evidence
  query_weather: evidence
  get_zone_operating_status: evidence
  predict_soil_moisture: analysis
  recommend_irrigation_plan: analysis
  create_irrigation_plan: planning
instruction_append: |
  当本技能激活时，优先保证计划生成链路完整：
  1. 先读农场上下文与分区状态。
  2. 再核对湿度、天气、预测和当前活跃计划。
  3. 最后才生成结构化计划，并明确风险、审批要求和建议时长。
---
本技能聚焦“证据充分再生成计划”，不允许跳过天气与湿度风险检查。
