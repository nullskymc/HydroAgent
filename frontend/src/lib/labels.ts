export const STATUS_LABELS: Record<string, string> = {
  idle: '空闲',
  ready: '已就绪',
  running: '运行中',
  stopped: '已停止',
  completed: '已完成',
  executed: '已执行',
  executing: '执行中',
  generated: '已生成',
  pending: '待处理',
  pending_approval: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  superseded: '已替换',
  cancelled: '已取消',
  open: '打开',
  acknowledged: '已确认',
  resolved: '已解决',
  success: '成功',
  error: '错误',
  healthy: '健康',
  unknown: '未知',
}

export const PLAN_STAGE_LABELS: Record<string, string> = {
  generated: '已生成',
  pending: '待审批',
  pending_approval: '待审批',
  approved: '已批准',
  executed: '已执行',
  completed_or_rejected: '完成/拒绝',
}

export const RISK_LABELS: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
  none: '无风险',
  unknown: '未知风险',
}

export const ACTION_LABELS: Record<string, string> = {
  start: '启动灌溉',
  hold: '保持观望',
  defer: '延后处理',
  stop: '停止灌溉',
  manual_override: '手动覆盖',
}

export function labelFor(value?: string | null, dictionary: Record<string, string> = STATUS_LABELS) {
  if (!value) return '--'
  return dictionary[value] || STATUS_LABELS[value] || value
}
