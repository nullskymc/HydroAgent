'use client'

import { ReactNode, useMemo, useState, useTransition } from 'react'
import { useSearchParams } from 'next/navigation'
import { RuntimeSettings } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { ModelPickerDrawer } from '@/components/model-picker-drawer'

function parseSensorIds(value: string) {
  // 设置页按“每行一个传感器”编辑，再统一转换成后端需要的数组结构。
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

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
    <section id={id} className="settings-panel">
      <header className="settings-panel-header">
        <div className="settings-panel-heading">
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </header>
      <div className="settings-panel-body">{children}</div>
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
    <div className="settings-item">
      <div className="settings-item-copy">
        <strong>{label}</strong>
        <p>{detail}</p>
        <span className="settings-item-path">{path}</span>
      </div>
      <div className="settings-item-control">{control}</div>
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
    <div className="settings-item">
      <div className="settings-item-copy">
        <strong>{label}</strong>
        <p>{detail}</p>
        <span className="settings-item-path">{path}</span>
      </div>
      <div className="settings-item-value">{value}</div>
    </div>
  )
}

const navItems = [
  { id: 'general', label: '常规' },
  { id: 'knowledge', label: '知识引擎' },
  { id: 'irrigation', label: '灌溉策略' },
  { id: 'alarm', label: '报警策略' },
  { id: 'context', label: '运行上下文' },
] as const

type SettingsSectionId = (typeof navItems)[number]['id']

function resolveSection(value: string | null | undefined, fallback: SettingsSectionId) {
  return navItems.some((item) => item.id === value) ? (value as SettingsSectionId) : fallback
}

export function SettingsForm({
  initialSettings,
  initialSection,
}: {
  initialSettings: RuntimeSettings
  initialSection: SettingsSectionId
}) {
  const [settings, setSettings] = useState(initialSettings)
  const [sensorIdsText, setSensorIdsText] = useState((initialSettings.sensor_ids || []).join('\n'))
  const [openAiApiKeyInput, setOpenAiApiKeyInput] = useState('')
  const [embeddingApiKeyInput, setEmbeddingApiKeyInput] = useState('')
  const [modelDrawerTarget, setModelDrawerTarget] = useState<'chat' | 'embedding' | null>(null)
  const [message, setMessage] = useState<string | null>(null)
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
          sensor_ids: parseSensorIds(sensorIdsText),
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
      setSensorIdsText((payload.settings.sensor_ids || []).join('\n'))
      setOpenAiApiKeyInput('')
      setEmbeddingApiKeyInput('')
      setMessage(
        payload.agent_reload_error
          ? `配置已保存，但 Agent 热重载失败：${payload.agent_reload_error}`
          : payload.agent_reloaded
            ? '配置已同步到 config.yaml，并已热重载 AI 引擎'
            : '配置已同步到 config.yaml'
      )
    })
  }

  const currentSection = useMemo(
    () => navItems.find((item) => item.id === activeSection) || navItems[0],
    [activeSection],
  )
  const configSourceLabel = formatConfigSourceLabel(settings.config_source)

  function applyModelSelection(modelId: string) {
    if (modelDrawerTarget === 'chat') {
      update('model_name', modelId)
    }
    if (modelDrawerTarget === 'embedding') {
      update('embedding_model_name', modelId)
    }
    setModelDrawerTarget(null)
  }

  function renderCurrentSection() {
    switch (activeSection) {
      case 'general':
        return (
          <SettingsSection id="general" title="常规" description="聊天模型、推理 endpoint、采集周期和传感器列表。">
            <SettingsItem
              label="聊天模型"
              path="model_name"
              detail="用于 LangChain 智能体主对话的模型名称。"
              control={
                <div className="settings-control-stack">
                  <Input
                    value={settings.model_name || ''}
                    onChange={(event) => update('model_name', event.target.value)}
                    placeholder="例如 gpt-4o"
                  />
                  <div className="settings-inline-actions">
                    <Button variant="secondary" size="sm" onClick={() => setModelDrawerTarget('chat')}>
                      从模型列表选择
                    </Button>
                  </div>
                </div>
              }
            />
            <SettingsItem
              label="推理 Endpoint"
              path="openai_base_url"
              detail="用于 Chat 与 Embeddings 的 OpenAI 兼容 API 地址。"
              control={
                <Input
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
                  type="password"
                  value={openAiApiKeyInput}
                  onChange={(event) => setOpenAiApiKeyInput(event.target.value)}
                  placeholder="输入新的 API Key"
                />
              }
            />
            <SettingsItem
              label="采集周期"
              path="sensors.collection_interval_minutes"
              detail="控制传感器数据采集的分钟间隔。"
              control={
                <Input
                  type="number"
                  value={settings.collection_interval_minutes ?? ''}
                  onChange={(event) => update('collection_interval_minutes', Number(event.target.value))}
                  placeholder="例如 60"
                />
              }
            />
            <SettingsItem
              label="传感器列表"
              path="sensors.ids"
              detail="每行一个传感器 ID，保存时映射成 YAML 数组。"
              control={
                <Textarea
                  rows={3}
                  value={sensorIdsText}
                  onChange={(event) => setSensorIdsText(event.target.value)}
                  placeholder={'sensor_001\nsensor_002'}
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
                <div className="settings-control-stack">
                  <Input
                    value={settings.embedding_model_name || ''}
                    onChange={(event) => update('embedding_model_name', event.target.value)}
                    placeholder="例如 text-embedding-3-small"
                  />
                  <div className="settings-inline-actions">
                    <Button variant="secondary" size="sm" onClick={() => setModelDrawerTarget('embedding')}>
                      从模型列表选择
                    </Button>
                  </div>
                </div>
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
          <SettingsSection id="irrigation" title="灌溉策略" description="默认阈值与默认灌溉时长。">
            <SettingsItem
              label="土壤湿度阈值 (%)"
              path="irrigation_strategy.soil_moisture_threshold"
              detail="低于该值时，系统更倾向于生成灌溉计划。"
              control={
                <Input
                  type="number"
                  value={settings.soil_moisture_threshold}
                  onChange={(event) => update('soil_moisture_threshold', Number(event.target.value))}
                />
              }
            />
            <SettingsItem
              label="默认灌溉时长 (分钟)"
              path="irrigation_strategy.default_duration_minutes"
              detail="缺少补偿因子时，作为计划与手动执行的基准时长。"
              control={
                <Input
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
          <SettingsSection id="alarm" title="报警策略" description="报警阈值和报警开关。">
            <SettingsItem
              label="报警阈值 (%)"
              path="alarm.soil_moisture_threshold"
              detail="低于该值时，监控链路会提升告警等级。"
              control={
                <Input
                  type="number"
                  value={settings.alarm_threshold}
                  onChange={(event) => update('alarm_threshold', Number(event.target.value))}
                />
              }
            />
            <SettingsItem
              label="启用报警"
              path="alarm.enabled"
              detail="控制是否主动发送低湿度报警。"
              control={
                <label className="settings-switch-row">
                  <input
                    className="ui-checkbox settings-switch-checkbox"
                    type="checkbox"
                    checked={settings.alarm_enabled}
                    onChange={(event) => update('alarm_enabled', event.target.checked)}
                  />
                  <span>{settings.alarm_enabled ? '已启用' : '已关闭'}</span>
                </label>
              }
            />
          </SettingsSection>
        )
      case 'context':
        return (
          <SettingsSection id="context" title="运行上下文" description="确认当前配置生效位置与运行实例上下文。">
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
      default:
        return null
    }
  }

  return (
    <div className="settings-workspace">
      <ModelPickerDrawer
        open={modelDrawerTarget !== null}
        title={modelDrawerTarget === 'embedding' ? '选择 Embeddings 模型' : '选择聊天模型'}
        selectedModel={modelDrawerTarget === 'embedding' ? settings.embedding_model_name : settings.model_name}
        onClose={() => setModelDrawerTarget(null)}
        onSelect={applyModelSelection}
      />
      <aside className="settings-sidebar">
        <div className="settings-sidebar-header">
          <p className="eyebrow">系统设置</p>
          <h1>系统设置</h1>
          <span title={settings.config_source || 'config.yaml'}>{configSourceLabel}</span>
        </div>
        <nav className="settings-sidebar-nav" aria-label="设置分组">
          {navItems.map((item) => (
            <a
              key={item.id}
              href={`/settings?section=${item.id}`}
              className={cn('settings-sidebar-link', activeSection === item.id && 'is-active')}
              aria-current={activeSection === item.id ? 'true' : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="settings-sidebar-note">
          <p>结构化映射到后端配置文件。</p>
        </div>
      </aside>

      <div className="settings-main">
        <header className="settings-main-header">
          <div className="settings-main-copy">
            <p className="eyebrow">系统偏好</p>
            <h2>{currentSection.label}</h2>
            <p>当前仅显示所选分类；字段继续通过结构化映射写入运行配置。</p>
          </div>
          <span className="settings-main-source" title={settings.config_source || 'config.yaml'}>
            {configSourceLabel}
          </span>
        </header>

        <div key={activeSection} className="settings-section-stage">
          {renderCurrentSection()}
        </div>

        <div className="settings-savebar">
          <Button className="settings-save-button" disabled={isPending} onClick={submit}>
            {isPending ? '保存中...' : '保存设置'}
          </Button>
          {message ? <span className="settings-save-message">{message}</span> : null}
        </div>
      </div>
    </div>
  )
}
