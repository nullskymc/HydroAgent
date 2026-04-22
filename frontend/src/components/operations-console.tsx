'use client'

import { FormEvent, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, Play, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet, apiSend } from '@/lib/api-client'
import { ACTION_LABELS, RISK_LABELS, labelFor } from '@/lib/labels'
import { DashboardData, HistoryData, IrrigationPlan, UserProfile, Zone } from '@/lib/types'
import { formatNumber1, formatPercent1, toNumber } from '@/lib/format'
import { cn, formatDateTime } from '@/lib/utils'

type ZoneView = {
  zone: Zone
  soilMoisture: number
  threshold: number
  deficit: number
  actuator?: Zone['actuators'][number]
  activePlan?: IrrigationPlan
}

type PlanAction = 'approve' | 'reject' | 'execute'

type GeneratePlanResponse = {
  plan?: IrrigationPlan | null
  suggestion?: {
    suggestion_id?: string
    proposed_action?: string
    risk_level?: string
    zone_name?: string | null
    recommended_duration_minutes?: number
    reasoning_summary?: string | null
  } | null
  reused_existing?: boolean
  suggestion_only?: boolean
}

const ACTIVE_PLAN_STATUSES = new Set(['pending_approval', 'approved', 'executing'])

function isActivePlan(plan: IrrigationPlan) {
  return ACTIVE_PLAN_STATUSES.has(plan.status) || plan.execution_status === 'executing'
}

function toneForRisk(value?: string | null): 'default' | 'success' | 'warning' | 'danger' {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  if (value === 'low') return 'success'
  return 'default'
}

function toneForState(value?: string | null): 'default' | 'success' | 'warning' | 'danger' {
  if (value === 'running' || value === 'executing') return 'warning'
  if (value === 'idle' || value === 'ready' || value === 'completed' || value === 'approved') return 'success'
  if (value === 'unknown' || value === 'error' || value === 'rejected') return 'danger'
  return 'default'
}

function MiniBadge({
  children,
  tone = 'default',
  className,
}: {
  children: React.ReactNode
  tone?: 'default' | 'success' | 'warning' | 'danger'
  className?: string
}) {
  const toneClass = {
    default: 'bg-slate-100 text-slate-600',
    success: 'bg-emerald-50 text-emerald-700',
    warning: 'bg-amber-50 text-amber-700',
    danger: 'bg-red-50 text-red-700',
  }[tone]

  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold leading-5', toneClass, className)}>
      {children}
    </span>
  )
}

function InlineStatusDot({ label, active = false }: { label: string; active?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500">
      {active ? <span className="size-2 animate-pulse rounded-full bg-[#0052FF] shadow-sm shadow-blue-500/30" aria-hidden="true" /> : null}
      <span>{label}</span>
    </span>
  )
}

function getSensorRows(dashboard: DashboardData) {
  return (dashboard.sensors?.sensors || []) as Array<Record<string, unknown>>
}

function buildZoneRows(dashboard: DashboardData, activePlans: IrrigationPlan[]): ZoneView[] {
  const sensorRows = getSensorRows(dashboard)
  return dashboard.zones.map((zone) => {
    const reading = sensorRows.find((row) => String(row.zone_id || '') === zone.zone_id)
    const soilMoisture = toNumber(reading?.soil_moisture)
    const threshold = toNumber(zone.soil_moisture_threshold, 40)
    return {
      zone,
      soilMoisture,
      threshold,
      deficit: Math.max(0, threshold - soilMoisture),
      actuator: zone.actuators[0],
      activePlan: activePlans.find((plan) => plan.zone_id === zone.zone_id),
    }
  })
}

function CompactEmpty({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-4 py-3">
      <strong className="block text-sm font-semibold text-slate-900">{title}</strong>
      <p className="m-0 mt-1 text-xs leading-5 text-slate-500">{description}</p>
    </div>
  )
}

function ZoneStatusPanel({ item }: { item: ZoneView }) {
  const severe = item.deficit >= 15
  const actuatorState = item.actuator?.status || 'unknown'
  const metrics = [
    { label: '湿度', value: formatPercent1(item.soilMoisture), valueClassName: severe ? 'text-red-700' : 'text-slate-900' },
    { label: '阈值', value: formatPercent1(item.threshold), valueClassName: 'text-slate-900' },
    { label: '缺口', value: formatPercent1(item.deficit), valueClassName: severe ? 'text-red-700' : 'text-slate-900' },
    { label: '设备', value: labelFor(actuatorState), valueClassName: 'text-slate-900' },
  ]

  return (
    <section className={cn('rounded-lg p-4 shadow-sm', severe ? 'border-l-4 border-red-500 bg-red-50' : 'bg-white')}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="m-0 truncate text-base font-semibold text-slate-900">{item.zone.name}</h3>
          <p className="m-0 mt-1 truncate text-xs text-slate-500">
            {item.zone.location} · {item.zone.crop_type || '未配置作物'}
          </p>
        </div>
        <MiniBadge tone={severe ? 'danger' : toneForState(actuatorState)}>
          {severe ? '缺水严重' : labelFor(actuatorState)}
        </MiniBadge>
      </div>

      <div className="mt-4 grid grid-cols-2 divide-y divide-slate-100 overflow-hidden rounded-md bg-white/80 md:grid-cols-4 md:divide-x md:divide-y-0">
        {metrics.map((metric) => (
          <div key={metric.label} className="min-h-16 px-3 py-2 first:pl-0 md:first:pl-3">
            <span className="block font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-500">{metric.label}</span>
            <strong className={cn('mt-1 block truncate text-2xl font-semibold leading-none', metric.valueClassName)}>
              {metric.value}
            </strong>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span>{item.actuator?.name || '未绑定执行器'}</span>
        {item.activePlan ? (
          <MiniBadge tone={toneForState(item.activePlan.status)}>
            {labelFor(item.activePlan.status)} · {formatNumber1(item.activePlan.recommended_duration_minutes, ' 分钟')}
          </MiniBadge>
        ) : (
          <span>暂无打开计划</span>
        )}
      </div>
    </section>
  )
}

function ZoneStatusList({ rows, loading }: { rows: ZoneView[]; loading: boolean }) {
  return (
    <section className="flex h-full flex-col rounded-lg bg-slate-50 p-3 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3 px-1">
        <div>
          <SectionBadge label="Zone Status" />
          <h2 className="m-0 mt-3 font-serif text-xl text-slate-950">分区状态</h2>
        </div>
        <InlineStatusDot active={loading} label={loading ? '同步中' : `${rows.length} 个分区`} />
      </div>

      {rows.length === 0 ? (
        <CompactEmpty title="暂无分区数据" description="当前调度台未读取到分区或传感器状态。" />
      ) : (
        <div className="flex flex-1 flex-col gap-3">
          {rows.map((item) => (
            <ZoneStatusPanel key={item.zone.zone_id} item={item} />
          ))}
        </div>
      )}
    </section>
  )
}

function GenerationResultNotice({ mutation }: { mutation: ReturnType<typeof useMutation<GeneratePlanResponse, Error, { zoneId: string; replace: boolean }>> }) {
  if (mutation.isError) {
    return (
      <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
        <strong className="block font-semibold">生成失败</strong>
        <span className="mt-1 block text-xs leading-5">{mutation.error.message}</span>
      </div>
    )
  }

  const result = mutation.data
  if (!result) return null

  if (result.plan) {
    return (
      <div className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
        <strong className="block font-semibold">{result.reused_existing ? '已复用已有活跃计划' : '已生成正式灌溉计划'}</strong>
        <span className="mt-1 block text-xs leading-5">
          {result.plan.zone_name || result.plan.zone_id || '未指定分区'} · {labelFor(result.plan.status)} · {formatNumber1(result.plan.recommended_duration_minutes, ' 分钟')}
        </span>
      </div>
    )
  }

  if (result.suggestion) {
    return (
      <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
        <strong className="block font-semibold">已记录暂缓建议，未生成执行计划</strong>
        <span className="mt-1 block text-xs leading-5">
          {result.suggestion.zone_name || '当前分区'} · {labelFor(result.suggestion.proposed_action, ACTION_LABELS)} · {labelFor(result.suggestion.risk_level, RISK_LABELS)}
        </span>
        {result.suggestion.reasoning_summary ? (
          <span className="mt-1 block max-h-10 overflow-hidden text-xs leading-5">{result.suggestion.reasoning_summary}</span>
        ) : null}
      </div>
    )
  }

  return null
}

function PlanGenerationForm({
  zones,
  currentUser,
  mutation,
}: {
  zones: Zone[]
  currentUser: UserProfile
  mutation: ReturnType<typeof useMutation<GeneratePlanResponse, Error, { zoneId: string; replace: boolean }>>
}) {
  const canCreate = currentUser.permissions.includes('plans:create')
  const enabledZones = zones.filter((zone) => zone.is_enabled)
  const [zoneId, setZoneId] = useState(enabledZones[0]?.zone_id || '')
  const [replace, setReplace] = useState(false)
  const selectedZoneId = enabledZones.some((zone) => zone.zone_id === zoneId) ? zoneId : enabledZones[0]?.zone_id || ''

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedZoneId || !canCreate) return
    mutation.mutate({ zoneId: selectedZoneId, replace })
  }

  return (
    <section className="rounded-lg bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <SectionBadge label="Plan Generator" />
          <h2 className="m-0 mt-3 font-serif text-xl text-slate-950">生成灌溉计划</h2>
        </div>
        {mutation.isPending ? <InlineStatusDot active label="生成中" /> : null}
      </div>

      <form className="grid gap-3" onSubmit={submit}>
        <label className="grid gap-1.5">
          <span className="text-xs font-medium text-slate-500">目标分区</span>
          <select
            className="h-9 rounded-lg bg-white px-3 text-sm text-slate-900 shadow-sm ring-1 ring-slate-100 transition focus:outline-none focus:ring-2 focus:ring-[#0052FF]/25 disabled:opacity-50"
            value={selectedZoneId}
            disabled={!canCreate || mutation.isPending || enabledZones.length === 0}
            onChange={(event) => setZoneId(event.target.value)}
          >
            {enabledZones.length === 0 ? <option value="">暂无可用分区</option> : null}
            {enabledZones.map((zone) => (
              <option key={zone.zone_id} value={zone.zone_id}>
                {zone.name} · {zone.location}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              className="size-4 rounded border-0 accent-[#0052FF]"
              checked={replace}
              disabled={!canCreate || mutation.isPending}
              onChange={(event) => setReplace(event.target.checked)}
            />
            替换已有打开计划
          </label>
          <span className="text-xs text-slate-500">同分区计划冲突时使用</span>
        </div>

        <Button
          type="submit"
          className="h-9 bg-gradient-to-r from-[#0052FF] to-[#4D7CFF] text-sm text-white shadow-sm shadow-blue-500/20 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-blue-500/25"
          disabled={!canCreate || mutation.isPending || !selectedZoneId}
        >
          {mutation.isPending ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="size-4" aria-hidden="true" />}
          生成计划
        </Button>
      </form>

      {!canCreate ? <p className="m-0 mt-3 text-xs text-slate-500">当前账号没有生成灌溉计划权限。</p> : null}
      <GenerationResultNotice mutation={mutation} />
    </section>
  )
}

function PlanActionButtons({
  plan,
  currentUser,
  mutation,
}: {
  plan: IrrigationPlan
  currentUser: UserProfile
  mutation: ReturnType<typeof useMutation<unknown, Error, { planId: string; action: PlanAction }>>
}) {
  const canApprove = currentUser.permissions.includes('plans:approve')
  const canExecute = currentUser.permissions.includes('plans:execute')

  if (plan.status === 'pending_approval' && canApprove) {
    return (
      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          className="inline-flex size-7 items-center justify-center rounded-md bg-emerald-50 text-emerald-700 transition hover:-translate-y-0.5 hover:bg-emerald-100 disabled:opacity-50"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate({ planId: plan.plan_id, action: 'approve' })}
          aria-label="批准计划"
        >
          <Check className="size-3.5" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="inline-flex size-7 items-center justify-center rounded-md bg-red-50 text-red-700 transition hover:-translate-y-0.5 hover:bg-red-100 disabled:opacity-50"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate({ planId: plan.plan_id, action: 'reject' })}
          aria-label="拒绝计划"
        >
          <X className="size-3.5" aria-hidden="true" />
        </button>
      </div>
    )
  }

  if (plan.status === 'approved' && canExecute) {
    return (
      <button
        type="button"
        className="inline-flex h-7 items-center justify-center gap-1 rounded-md bg-blue-50 px-2 text-xs font-semibold text-[#0052FF] transition hover:-translate-y-0.5 hover:bg-blue-100 disabled:opacity-50"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate({ planId: plan.plan_id, action: 'execute' })}
      >
        <Play className="size-3.5" aria-hidden="true" />
        执行
      </button>
    )
  }

  return <span className="text-xs text-slate-500">--</span>
}

function ActivePlanList({
  plans,
  currentUser,
  mutation,
  loading,
}: {
  plans: IrrigationPlan[]
  currentUser: UserProfile
  mutation: ReturnType<typeof useMutation<unknown, Error, { planId: string; action: PlanAction }>>
  loading: boolean
}) {
  return (
    <section className="flex flex-1 flex-col rounded-lg bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <SectionBadge label="Active Plans" />
          <h2 className="m-0 mt-3 font-serif text-xl text-slate-950">活跃计划</h2>
        </div>
        <InlineStatusDot active={loading} label={loading ? '同步中' : `${plans.length} 条`} />
      </div>

      {plans.length === 0 ? (
        <CompactEmpty title="暂无活跃计划" description="当前没有待审批、已批准或正在执行的计划。" />
      ) : (
        <div className="overflow-hidden rounded-lg bg-slate-50">
          <div className="grid h-9 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 px-3 font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-500">
            <span>分区 / 动作</span>
            <span>状态</span>
            <span className="text-right">操作</span>
          </div>
          <div className="divide-y divide-slate-100">
            {plans.map((plan) => (
              <div key={plan.plan_id} className="grid min-h-11 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 bg-white px-3 py-2">
                <div className="min-w-0">
                  <strong className="block truncate text-sm font-semibold text-slate-900">{plan.zone_name || plan.zone_id || '未指定分区'}</strong>
                  <span className="block truncate text-xs text-slate-500">
                    {labelFor(plan.proposed_action, ACTION_LABELS)} · {formatNumber1(plan.recommended_duration_minutes, ' 分钟')} · {formatDateTime(plan.created_at)}
                  </span>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <MiniBadge tone={toneForState(plan.status)}>{labelFor(plan.status)}</MiniBadge>
                  <MiniBadge tone={toneForRisk(plan.risk_level)}>{labelFor(plan.risk_level, RISK_LABELS)}</MiniBadge>
                </div>
                <PlanActionButtons plan={plan} currentUser={currentUser} mutation={mutation} />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

export function OperationsConsole({
  initialHistory,
  initialDashboard,
  currentUser,
}: {
  initialHistory: HistoryData
  initialDashboard: DashboardData
  currentUser: UserProfile
}) {
  const queryClient = useQueryClient()
  const historyQuery = useQuery({
    queryKey: ['history'],
    queryFn: () => apiGet<HistoryData>('/api/history'),
    initialData: initialHistory,
    refetchInterval: 10_000,
  })
  const dashboardQuery = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => apiGet<DashboardData>('/api/dashboard'),
    initialData: initialDashboard,
    refetchInterval: 5_000,
  })
  const planActionMutation = useMutation({
    mutationFn: ({ planId, action }: { planId: string; action: PlanAction }) =>
      apiSend(`/api/plans/${planId}/${action}`, 'POST', { actor: currentUser.username }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const generatePlanMutation = useMutation({
    mutationFn: ({ zoneId, replace }: { zoneId: string; replace: boolean }) =>
      apiSend<GeneratePlanResponse>('/api/plans', 'POST', {
        zone_id: zoneId,
        trigger: 'operations-console',
        replace,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const activePlans = useMemo(
    () => (historyQuery.data?.active_plans || historyQuery.data?.plans || []).filter(isActivePlan),
    [historyQuery.data?.active_plans, historyQuery.data?.plans],
  )
  const zoneRows = useMemo(() => buildZoneRows(dashboardQuery.data, activePlans), [dashboardQuery.data, activePlans])

  return (
    <div className="grid h-full grid-cols-1 items-stretch gap-4 lg:grid-cols-12">
      <div className="flex h-full min-w-0 flex-col lg:col-span-7">
        <ZoneStatusList rows={zoneRows} loading={dashboardQuery.isFetching} />
      </div>

      <div className="flex h-full min-w-0 flex-col gap-4 lg:col-span-5">
        <PlanGenerationForm zones={dashboardQuery.data.zones} currentUser={currentUser} mutation={generatePlanMutation} />
        <ActivePlanList plans={activePlans} currentUser={currentUser} mutation={planActionMutation} loading={historyQuery.isFetching} />
      </div>
    </div>
  )
}
