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
        <p className="eyebrow">数据层</p>
        <h2>{title}</h2>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  )
}
