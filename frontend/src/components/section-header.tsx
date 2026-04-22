import { SectionBadge } from '@/components/ui/section-badge'

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <div className="section-header">
      <div className="section-header-copy">
        <SectionBadge label="Data Layer" />
        <h2>{title}</h2>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  )
}
