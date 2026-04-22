import { ReactNode } from 'react'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'

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
        <SectionBadge label={eyebrow} />
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
  return <EmptyState title={title} description={detail} />
}
