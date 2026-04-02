import { ReactNode } from 'react'

export function ConsoleSectionHeader({
  eyebrow,
  title,
  meta,
}: {
  eyebrow: string
  title: string
  meta?: ReactNode
}) {
  return (
    <header className="console-section-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {meta ? <div className="console-section-meta">{meta}</div> : null}
    </header>
  )
}

// 统一控制台空态，让离线、无数据、未配置等场景保持一致的视觉语义。
export function ConsoleEmptyState({
  title,
  detail,
}: {
  title: string
  detail: string
}) {
  return (
    <div className="console-empty-state" aria-live="polite">
      <div className="console-empty-skeleton" />
      <div className="console-empty-skeleton console-empty-skeleton-short" />
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  )
}
