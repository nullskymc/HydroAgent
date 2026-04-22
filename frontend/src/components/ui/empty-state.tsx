import { LucideIcon, Sprout } from 'lucide-react'
import { cn } from '@/lib/utils'

export function EmptyState({
  title,
  description,
  icon: Icon = Sprout,
  className,
}: {
  title: string
  description?: string
  icon?: LucideIcon
  className?: string
}) {
  return (
    <div className={cn('flex min-h-24 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-200 bg-slate-50/60 p-4 text-center', className)}>
      <div className="flex size-8 items-center justify-center rounded-md bg-white text-slate-400 shadow-sm">
        <Icon className="size-4" aria-hidden="true" />
      </div>
      <div className="flex flex-col gap-1">
        <strong className="text-sm font-semibold text-slate-700">{title}</strong>
        {description ? <p className="max-w-sm text-xs leading-5 text-slate-500">{description}</p> : null}
      </div>
    </div>
  )
}
