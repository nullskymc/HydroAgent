'use client'

import { ReactNode, useEffect, useMemo, useState, useTransition } from 'react'
import { useSearchParams } from 'next/navigation'
import { RuntimeSettings, SkillCatalogItem } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { ModelPickerDrawer } from '@/components/model-picker-drawer'
import { Badge } from '@/components/ui/badge'

function formatConfigSourceLabel(value?: string) {
  if (!value) {
    return 'config.yaml'
  }

  const segments = value.split(/[\\/]/).filter(Boolean)
  return segments[segments.length - 1] || value
}

function formatSecretStatusLabel(configured?: boolean, maskedValue?: string | null) {
  if (!configured) {
    return '未配置'
  }
  return maskedValue || '已配置'
}

const compactInputClass =
  'h-9 max-w-md rounded-md border-slate-200 bg-slate-50 shadow-none focus-visible:ring-2 focus-visible:ring-blue-500/20'
const compactNumberInputClass =
  'h-8 w-24 rounded-md border-slate-200 bg-slate-50 px-2 text-sm shadow-none focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-[#0052FF]/20'
const compactTextareaClass =
  'min-h-44 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm shadow-none ring-0 transition-all focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-[#0052FF]/20'
const primaryActionClass =
  'h-9 rounded-md bg-gradient-to-r from-[#0052FF] to-[#4D7CFF] px-4 text-white shadow-sm transition-transform hover:-translate-y-0.5'
const secondaryActionClass =
  'h-9 rounded-md border border-slate-200 bg-white px-4 text-slate-700 shadow-none hover:bg-slate-50 hover:shadow-none hover:translate-y-0'
const checkboxClass = 'size-4 rounded border-slate-300 text-[#0052FF] focus:ring-2 focus:ring-blue-500/20'

function SettingsSection({
  id,
  title,
  description,
  children,
}: {
  id: string
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section id={id} className="bg-white">
      <header className="border-b border-slate-100 pb-5">
        <h2 className="m-0 text-base font-semibold text-slate-950">{title}</h2>
        <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">{description}</p>
      </header>
      <div>{children}</div>
    </section>
  )
}

function SettingsItem({
  label,
  path,
  detail,
  control,
}: {
  label: string
  path: string
  detail: string
  control: ReactNode
}) {
  return (
    <div className="grid grid-cols-1 gap-4 border-b border-slate-100 py-5 md:grid-cols-12 md:gap-6">
      <div className="md:col-span-4">
        <strong className="block text-sm font-medium text-slate-900">{label}</strong>
        <p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p>
        <span className="mt-2 block font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-400">{path}</span>
      </div>
      <div className="min-w-0 md:col-span-8">{control}</div>
    </div>
  )
}

function ReadonlyItem({
  label,
  path,
  value,
  detail,
}: {
  label: string
  path: string
  value: string
  detail: string
}) {
  return (
    <div className="grid grid-cols-1 gap-4 border-b border-slate-100 py-5 md:grid-cols-12 md:gap-6">
      <div className="md:col-span-4">
        <strong className="block text-sm font-medium text-slate-900">{label}</strong>
        <p className="mt-1 text-xs leading-5 text-slate-500">{detail}</p>
        <span className="mt-2 block font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-400">{path}</span>
      </div>
      <div className="min-w-0 md:col-span-8">
        <div className="max-w-md truncate rounded-md bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700">{value}</div>
      </div>
    </div>
  )
}

const navItems = [
  { id: 'general', label: '常规' },
  { id: 'knowledge', label: '知识引擎' },
  { id: 'irrigation', label: '灌溉策略' },
  { id: 'alarm', label: '报警策略' },
  { id: 'context', label: '运行上下文' },
  { id: 'skills', label: 'Skills' },
] as const

type SettingsSectionId = (typeof navItems)[number]['id']

function resolveSection(value: string | null | undefined, fallback: SettingsSectionId) {
  return navItems.some((item) => item.id === value) ? (value as SettingsSectionId) : fallback
}

function formatSkillSourceLabel(value?: string | null) {
  if (value === 'generated') return '系统包装'
  if (value === 'imported') return '外部导入'
  return '项目内置'
}

// 小型布局组件只负责视觉约束，业务状态仍留在 SettingsForm 中。
function ControlStack({ children }: { children: ReactNode }) {
  return <div className="flex min-w-0 max-w-md flex-col gap-2">{children}</div>
}

function InlineActions({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>
}

function SwitchRow({ children }: { children: ReactNode }) {
  return <label className="flex flex-wrap items-center gap-2 text-sm text-slate-600">{children}</label>
}

export function SettingsForm({
  initialSettings,
  initialSection,
}: {
  initialSettings: RuntimeSettings
  initialSection: SettingsSectionId
}) {
  const [settings, setSettings] = useState(initialSettings)
  const [openAiApiKeyInput, setOpenAiApiKeyInput] = useState('')
  const [embeddingApiKeyInput, setEmbeddingApiKeyInput] = useState('')
  const [modelDrawerTarget, setModelDrawerTarget] = useState<'chat' | 'embedding' | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [skillMessage, setSkillMessage] = useState<string | null>(null)
  const [skills, setSkills] = useState<SkillCatalogItem[]>([])
  const [selectedSkill, setSelectedSkill] = useState<SkillCatalogItem | null>(null)
  const [importUrl, setImportUrl] = useState('')
  const [importOverwrite, setImportOverwrite] = useState(false)
  const [isPending, startTransition] = useTransition()
  const searchParams = useSearchParams()
  const activeSection = resolveSection(searchParams?.get('section'), initialSection)

  function update<K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }))
  }

  function submit() {
    startTransition(async () => {
      setMessage(null)
      const response = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_name: settings.model_name,
          embedding_model_name: settings.embedding_model_name,
          openai_base_url: settings.openai_base_url,
          knowledge_top_k: settings.knowledge_top_k,
          knowledge_chunk_size: settings.knowledge_chunk_size,
          knowledge_chunk_overlap: settings.knowledge_chunk_overlap,
          collection_interval_minutes: settings.collection_interval_minutes,
          soil_moisture_threshold: settings.soil_moisture_threshold,
          default_duration_minutes: settings.default_duration_minutes,
          alarm_threshold: settings.alarm_threshold,
          alarm_enabled: settings.alarm_enabled,
          ...(openAiApiKeyInput.trim() ? { openai_api_key: openAiApiKeyInput.trim() } : {}),
          ...(embeddingApiKeyInput.trim() ? { embedding_api_key: embeddingApiKeyInput.trim() } : {}),
        }),
      })

      if (!response.ok) {
        setMessage(await response.text())
        return
      }

      const payload = await response.json()
      setSettings(payload.settings)
      setOpenAiApiKeyInput('')
      setEmbeddingApiKeyInput('')
      setMessage(
        payload.agent_reload_error
          ? `配置已保存，但 AI 引擎热重载失败：${payload.agent_reload_error}`
          : payload.agent_reloaded
            ? 'YAML 与业务配置已保存，并已热重载 AI 引擎'
            : 'YAML 与业务配置已保存'
      )
    })
  }

  const currentSection = useMemo(
    () => navItems.find((item) => item.id === activeSection) || navItems[0],
    [activeSection],
  )
  const configSourceLabel = formatConfigSourceLabel(settings.config_source)

  useEffect(() => {
    if (activeSection !== 'skills') return
    let cancelled = false

    async function loadSkillWorkspace() {
      try {
        const skillsResponse = await fetch('/api/skills', { cache: 'no-store' })
        const skillsPayload = skillsResponse.ok ? ((await skillsResponse.json()) as { skills?: SkillCatalogItem[] }) : { skills: [] }
        if (cancelled) return
        setSkills(skillsPayload.skills || [])
        setSelectedSkill((current) => {
          if (!current) return skillsPayload.skills?.[0] || null
          return (skillsPayload.skills || []).find((item) => item.id === current.id) || null
        })
      } catch (error) {
        if (!cancelled) {
          setSkillMessage(error instanceof Error ? error.message : 'Skill 列表加载失败')
        }
      }
    }

    void loadSkillWorkspace()
    return () => {
      cancelled = true
    }
  }, [activeSection])

  async function refreshSkillWorkspace(preferredSkillId?: string) {
    const skillsResponse = await fetch('/api/skills', { cache: 'no-store' })
    const skillsPayload = (await skillsResponse.json()) as { skills?: SkillCatalogItem[] }
    const nextSkills = skillsPayload.skills || []
    setSkills(nextSkills)
    const nextSelected =
      (preferredSkillId ? nextSkills.find((item) => item.id === preferredSkillId) : null) ||
      nextSkills.find((item) => item.id === selectedSkill?.id) ||
      nextSkills[0] ||
      null
    if (!nextSelected) {
      setSelectedSkill(null)
      return
    }
    const detailResponse = await fetch(`/api/skills/${nextSelected.id}`, { cache: 'no-store' })
    if (!detailResponse.ok) {
      setSelectedSkill(nextSelected)
      return
    }
    const detailPayload = (await detailResponse.json()) as { skill: SkillCatalogItem }
    setSelectedSkill(detailPayload.skill)
  }

  function applyModelSelection(modelId: string) {
    if (modelDrawerTarget === 'chat') {
      update('model_name', modelId)
    }
    if (modelDrawerTarget === 'embedding') {
      update('embedding_model_name', modelId)
    }
    setModelDrawerTarget(null)
  }

  function loadSkillDetail(skillId: string) {
    startTransition(async () => {
      setSkillMessage(null)
      const response = await fetch(`/api/skills/${skillId}`, { cache: 'no-store' })
      if (!response.ok) {
        setSkillMessage(await response.text())
        return
      }
      const payload = (await response.json()) as { skill: SkillCatalogItem }
      setSelectedSkill(payload.skill)
    })
  }

  function submitSkillImport(urlOverride?: string, overwriteOverride?: boolean) {
    startTransition(async () => {
      setSkillMessage(null)
      const response = await fetch('/api/skills/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: (urlOverride ?? importUrl).trim(),
          overwrite: overwriteOverride ?? importOverwrite,
        }),
      })
      const payload = (await response.json().catch(() => null)) as
        | { detail?: string; import_result?: string; skill?: SkillCatalogItem }
        | null
      if (!response.ok) {
        setSkillMessage(payload?.detail || 'Skill 导入失败')
        return
      }
      setSkillMessage(payload?.import_result === 'updated' ? 'Skill 已覆盖更新' : 'Skill 已导入')
      setImportOverwrite(false)
      setImportUrl('')
      await refreshSkillWorkspace(payload?.skill?.id)
    })
  }

  function deleteManagedSkill(skillId: string) {
    startTransition(async () => {
      setSkillMessage(null)
      const response = await fetch(`/api/skills/${skillId}`, { method: 'DELETE' })
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      if (!response.ok) {
        setSkillMessage(payload?.detail || 'Skill 删除失败')
        return
      }
      setSkillMessage('Skill 已删除')
      await refreshSkillWorkspace()
    })
  }

  function renderCurrentSection() {
    switch (activeSection) {
      case 'general':
        return (
          <SettingsSection id="general" title="常规" description="YAML 托管的聊天模型、推理 endpoint 与基础业务节奏。">
            <SettingsItem
              label="聊天模型"
              path="model_name"
              detail="用于 LangChain 智能体主对话的模型名称。"
              control={
                <ControlStack>
                  <Input
                    className={compactInputClass}
                    value={settings.model_name || ''}
                    onChange={(event) => update('model_name', event.target.value)}
                    placeholder="例如 gpt-4o"
                  />
                  <InlineActions>
                    <Button className={secondaryActionClass} variant="secondary" onClick={() => setModelDrawerTarget('chat')}>
                      从模型列表选择
                    </Button>
                  </InlineActions>
                </ControlStack>
              }
            />
            <SettingsItem
              label="推理 Endpoint"
              path="openai_base_url"
              detail="用于 Chat 与 Embeddings 的 OpenAI 兼容 API 地址。"
              control={
                <Input
                  className={compactInputClass}
                  value={settings.openai_base_url || ''}
                  onChange={(event) => update('openai_base_url', event.target.value)}
                  placeholder="例如 https://api.openai.com/v1"
                />
              }
            />
            <ReadonlyItem
              label="聊天 API Key 状态"
              path="openai_api_key_encrypted"
              value={formatSecretStatusLabel(settings.openai_api_key_status?.configured, settings.openai_api_key_status?.masked_value)}
              detail="只返回掩码状态，明文不会回传前端。"
            />
            <SettingsItem
              label="覆盖聊天 API Key"
              path="openai_api_key"
              detail="留空表示不修改；保存时仅单向写入后端加密配置。"
              control={
                <Input
                  className={compactInputClass}
                  type="password"
                  value={openAiApiKeyInput}
                  onChange={(event) => setOpenAiApiKeyInput(event.target.value)}
                  placeholder="输入新的 API Key"
                />
              }
            />
            <SettingsItem
              label="采集周期"
              path="system_settings.collection_interval_minutes"
              detail="数据库中的全局默认采集周期，影响自动检查与采样节奏。"
              control={
                <Input
                  className={compactNumberInputClass}
                  type="number"
                  value={settings.collection_interval_minutes ?? ''}
                  onChange={(event) => update('collection_interval_minutes', Number(event.target.value))}
                  placeholder="例如 60"
                />
              }
            />
          </SettingsSection>
        )
      case 'knowledge':
        return (
          <SettingsSection id="knowledge" title="知识引擎" description="Embeddings 模型、知识库切片与召回参数。">
            <SettingsItem
              label="Embeddings 模型"
              path="embedding_model_name"
              detail="用于知识库切片向量化与语义检索。"
              control={
                <ControlStack>
                  <Input
                    className={compactInputClass}
                    value={settings.embedding_model_name || ''}
                    onChange={(event) => update('embedding_model_name', event.target.value)}
                    placeholder="例如 text-embedding-3-small"
                  />
                  <InlineActions>
                    <Button className={secondaryActionClass} variant="secondary" onClick={() => setModelDrawerTarget('embedding')}>
                      从模型列表选择
                    </Button>
                  </InlineActions>
                </ControlStack>
              }
            />
            <ReadonlyItem
              label="Embeddings Key 状态"
              path="embedding_api_key_encrypted"
              value={formatSecretStatusLabel(settings.embedding_api_key_status?.configured, settings.embedding_api_key_status?.masked_value)}
              detail="未单独配置时，后端会回退到聊天 API Key。"
            />
            <SettingsItem
              label="覆盖 Embeddings Key"
              path="embedding_api_key"
              detail="留空表示继续沿用当前配置；保存时只写入密文。"
              control={
                <Input
                  className={compactInputClass}
                  type="password"
                  value={embeddingApiKeyInput}
                  onChange={(event) => setEmbeddingApiKeyInput(event.target.value)}
                  placeholder="输入新的 Embeddings Key"
                />
              }
            />
            <SettingsItem
              label="默认召回条数"
              path="knowledge_base.top_k"
              detail="聊天检索工具默认返回的知识片段数量。"
              control={
                <Input
                  className={compactNumberInputClass}
                  type="number"
                  value={settings.knowledge_top_k ?? ''}
                  onChange={(event) => update('knowledge_top_k', Number(event.target.value))}
                  placeholder="例如 4"
                />
              }
            />
            <SettingsItem
              label="切片长度"
              path="knowledge_base.chunk_size"
              detail="单个知识切片的字符上限。"
              control={
                <Input
                  className={compactNumberInputClass}
                  type="number"
                  value={settings.knowledge_chunk_size ?? ''}
                  onChange={(event) => update('knowledge_chunk_size', Number(event.target.value))}
                  placeholder="例如 1200"
                />
              }
            />
            <SettingsItem
              label="切片重叠"
              path="knowledge_base.chunk_overlap"
              detail="相邻知识切片之间保留的重叠字符数。"
              control={
                <Input
                  className={compactNumberInputClass}
                  type="number"
                  value={settings.knowledge_chunk_overlap ?? ''}
                  onChange={(event) => update('knowledge_chunk_overlap', Number(event.target.value))}
                  placeholder="例如 180"
                />
              }
            />
          </SettingsSection>
        )
      case 'irrigation':
        return (
          <SettingsSection id="irrigation" title="灌溉策略" description="数据库托管的新建分区默认值，不会覆盖现有分区。">
            <SettingsItem
              label="新建分区默认阈值 (%)"
              path="system_settings.default_soil_moisture_threshold"
              detail="创建新分区时预填的土壤湿度阈值；现有分区继续使用各自数据库值。"
              control={
                <Input
                  className={compactNumberInputClass}
                  type="number"
                  value={settings.soil_moisture_threshold}
                  onChange={(event) => update('soil_moisture_threshold', Number(event.target.value))}
                />
              }
            />
            <SettingsItem
              label="新建分区默认灌溉时长 (分钟)"
              path="system_settings.default_duration_minutes"
              detail="创建新分区时预填的默认时长；不会批量覆盖已有分区。"
              control={
                <Input
                  className={compactNumberInputClass}
                  type="number"
                  value={settings.default_duration_minutes}
                  onChange={(event) => update('default_duration_minutes', Number(event.target.value))}
                />
              }
            />
          </SettingsSection>
        )
      case 'alarm':
        return (
          <SettingsSection id="alarm" title="报警策略" description="数据库托管的全局报警默认值。">
            <SettingsItem
              label="报警阈值 (%)"
              path="system_settings.alarm_threshold"
              detail="低于该值时，全局告警规则会提升风险等级。"
              control={
                <Input
                  className={compactNumberInputClass}
                  type="number"
                  value={settings.alarm_threshold}
                  onChange={(event) => update('alarm_threshold', Number(event.target.value))}
                />
              }
            />
            <SettingsItem
              label="启用报警"
              path="system_settings.alarm_enabled"
              detail="控制是否启用全局低湿度报警链路。"
              control={
                <SwitchRow>
                  <input
                    className={checkboxClass}
                    type="checkbox"
                    checked={settings.alarm_enabled}
                    onChange={(event) => update('alarm_enabled', event.target.checked)}
                  />
                  <span>{settings.alarm_enabled ? '已启用' : '已关闭'}</span>
                </SwitchRow>
              }
            />
          </SettingsSection>
        )
      case 'context':
        return (
          <SettingsSection id="context" title="运行上下文" description="确认 YAML 来源与当前实例的运行环境。">
            <ReadonlyItem
              label="数据库类型"
              path="database.type"
              value={settings.db_type || '--'}
              detail="当前运行实例读取到的数据库类型。"
            />
            <ReadonlyItem
              label="配置文件路径"
              path="config.yaml"
              value={settings.config_source || '--'}
              detail="后端设置接口当前绑定的配置文件路径。"
            />
          </SettingsSection>
        )
      case 'skills':
        return (
          <>
            <SettingsSection id="skills-installed" title="已安装 Skills" description="统一查看项目内置、外部导入和系统预置包装的 skill。">
              <div className="grid gap-6 border-b border-slate-100 py-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
                <div className="max-h-[520px] overflow-y-auto pr-1">
                  <div className="divide-y divide-slate-100">
                    {skills.map((skill) => (
                      <button
                        key={skill.id}
                        type="button"
                        className={cn(
                          'block w-full px-3 py-3 text-left transition hover:bg-slate-50',
                          selectedSkill?.id === skill.id && 'rounded-md bg-blue-50 text-[#0052FF] hover:bg-blue-50',
                        )}
                        onClick={() => loadSkillDetail(skill.id)}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <strong className="text-sm font-medium text-slate-950">{skill.name}</strong>
                          <Badge tone={skill.source_type === 'generated' ? 'warning' : skill.source_type === 'imported' ? 'success' : 'default'}>
                            {formatSkillSourceLabel(skill.source_type)}
                          </Badge>
                        </div>
                        <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{skill.description}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-400">
                          <span>{skill.id}</span>
                          <span>{skill.tool_bundle?.length || skill.tool_allowlist?.length || 0} tools</span>
                          <span>{skill.workflow_phases?.join(' / ') || 'analysis'}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="min-w-0 bg-white">
                  {selectedSkill ? (
                    <div className="flex min-w-0 flex-col gap-4">
                      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                        <div className="min-w-0">
                          <strong className="text-sm font-semibold text-slate-950">{selectedSkill.name}</strong>
                          <p className="mt-1 text-xs leading-5 text-slate-500">{selectedSkill.description}</p>
                        </div>
                        <Badge>{formatSkillSourceLabel(selectedSkill.source_type)}</Badge>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-400">
                        <span>ID: {selectedSkill.id}</span>
                        <span>模式: {(selectedSkill.mode_allowlist || []).join(' / ') || '--'}</span>
                        <span>工具数: {selectedSkill.tool_bundle?.length || selectedSkill.tool_allowlist?.length || 0}</span>
                      </div>
                      {selectedSkill.source_url ? (
                        <a className="break-all text-xs font-medium text-[#0052FF] hover:underline" href={selectedSkill.source_url} target="_blank" rel="noreferrer">
                          {selectedSkill.source_url}
                        </a>
                      ) : null}
                      <Textarea className={compactTextareaClass} readOnly rows={8} value={selectedSkill.instruction_append || '暂无详细指令'} />
                      <InlineActions>
                        {selectedSkill.source_type === 'imported' && selectedSkill.source_url ? (
                          <Button
                            className={secondaryActionClass}
                            variant="secondary"
                            disabled={isPending}
                            onClick={() => submitSkillImport(selectedSkill.source_url || '', true)}
                          >
                            重新导入
                          </Button>
                        ) : null}
                        {selectedSkill.source_type === 'imported' ? (
                          <Button
                            className="h-8 rounded-md px-3 text-xs text-slate-600 hover:bg-slate-100"
                            size="sm"
                            variant="ghost"
                            disabled={isPending}
                            onClick={() => deleteManagedSkill(selectedSkill.id)}
                          >
                            删除
                          </Button>
                        ) : null}
                      </InlineActions>
                    </div>
                  ) : (
                    <div className="rounded-md bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700">当前没有已安装 skill。</div>
                  )}
                </div>
              </div>
            </SettingsSection>

            <SettingsSection id="skills-import" title="导入外部 Skill" description="仅支持 GitHub Raw 与白名单域名，下载后落盘为本地 skill。">
              <SettingsItem
                label="Skill 链接"
                path="skills.import.url"
                detail="支持 raw.githubusercontent.com、gist.githubusercontent.com，以及配置的白名单域名。GitHub blob 链接会自动转换成 raw。"
                control={
                  <ControlStack>
                    <Input
                      className={compactInputClass}
                      value={importUrl}
                      onChange={(event) => setImportUrl(event.target.value)}
                      placeholder="https://raw.githubusercontent.com/..."
                    />
                    <SwitchRow>
                      <input
                        className={checkboxClass}
                        type="checkbox"
                        checked={importOverwrite}
                        onChange={(event) => setImportOverwrite(event.target.checked)}
                      />
                      <span>{importOverwrite ? '允许覆盖已存在 imported/generated skill' : '默认禁止覆盖'}</span>
                    </SwitchRow>
                    <InlineActions>
                      <Button className={primaryActionClass} disabled={isPending || !importUrl.trim()} onClick={() => submitSkillImport()}>
                        导入 Skill
                      </Button>
                    </InlineActions>
                  </ControlStack>
                }
              />
            </SettingsSection>
          </>
        )
      default:
        return null
    }
  }

  return (
    <div className="flex min-h-full w-full flex-col gap-6 bg-white lg:flex-row">
      <ModelPickerDrawer
        open={modelDrawerTarget !== null}
        title={modelDrawerTarget === 'embedding' ? '选择 Embeddings 模型' : '选择聊天模型'}
        selectedModel={modelDrawerTarget === 'embedding' ? settings.embedding_model_name : settings.model_name}
        onClose={() => setModelDrawerTarget(null)}
        onSelect={applyModelSelection}
      />
      <aside className="w-full shrink-0 bg-white lg:sticky lg:top-4 lg:w-56 lg:self-start">
        <div className="mb-5">
          <p className="m-0 font-mono text-[0.64rem] font-semibold uppercase tracking-widest text-slate-400">系统设置</p>
          <h1 className="mt-2 text-lg font-semibold text-slate-950">系统设置</h1>
          <span className="mt-1 block truncate font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-400" title={settings.config_source || 'config.yaml'}>
            {configSourceLabel}
          </span>
        </div>
        <nav className="flex flex-row gap-1 overflow-x-auto lg:flex-col lg:overflow-visible" aria-label="设置分组">
          {navItems.map((item) => (
            <a
              key={item.id}
              href={`/settings?section=${item.id}`}
              className={cn(
                'whitespace-nowrap rounded-md px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50',
                activeSection === item.id && 'bg-blue-50 font-medium text-blue-600',
              )}
              aria-current={activeSection === item.id ? 'true' : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="mt-5 hidden text-xs leading-5 text-slate-500 lg:block">
          <p>模型配置写 YAML，业务默认值写数据库。</p>
        </div>
      </aside>

      <div className="min-w-0 max-w-4xl flex-1 bg-white px-4 md:px-8">
        <header className="flex flex-col justify-between gap-3 border-b border-slate-100 pb-6 md:flex-row md:items-end">
          <div>
            <p className="m-0 font-mono text-[0.64rem] font-semibold uppercase tracking-widest text-slate-400">系统偏好</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">{currentSection.label}</h2>
            <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-500">当前仅显示所选分类；模型配置写入 YAML，运行期业务默认值写入数据库。</p>
          </div>
          <span
            className="w-fit rounded-md bg-slate-50 px-3 py-2 font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-500"
            title={settings.config_source || 'config.yaml'}
          >
            {configSourceLabel}
          </span>
        </header>

        <div key={activeSection} className="pt-6">
          {renderCurrentSection()}
        </div>

        {activeSection === 'skills' && skillMessage ? (
          <div className="mt-4 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
            <p>{skillMessage}</p>
          </div>
        ) : null}

        <div className="sticky bottom-0 mt-6 flex flex-wrap items-center gap-3 border-t border-slate-100 bg-white/95 py-4 backdrop-blur">
          <Button className={primaryActionClass} disabled={isPending} onClick={submit}>
            {isPending ? '保存中...' : '保存设置'}
          </Button>
          {message ? <span className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">{message}</span> : null}
        </div>
      </div>
    </div>
  )
}
