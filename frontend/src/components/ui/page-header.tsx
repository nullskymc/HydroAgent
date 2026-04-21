import { Badge } from '@/components/ui/badge'
import { SectionBadge } from '@/components/ui/section-badge'
import { cn } from '@/lib/utils'

export function PageHeader({
  eyebrow,
  title,
  description,
  meta,
  action,
  compact = false,
}: {
  eyebrow: string
  title: string
  description?: string
  meta?: string[]
  action?: React.ReactNode
  compact?: boolean
}) {
  return (
    <header className={cn('page-header-block', compact && 'page-header-compact')}>
      <div className="page-header-copy">
        <SectionBadge label={eyebrow} />
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
        {meta?.length ? (
          <div className="page-meta-row">
            {meta.map((item) => (
              <Badge key={item}>{item}</Badge>
            ))}
          </div>
        ) : null}
      </div>
      {action ? <div className="page-header-action">{action}</div> : null}
    </header>
  )
}
