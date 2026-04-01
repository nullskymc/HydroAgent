import { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

type BadgeTone = 'default' | 'success' | 'warning' | 'danger'

const toneClasses: Record<BadgeTone, string> = {
  default: 'ui-badge',
  success: 'ui-badge ui-badge-success',
  warning: 'ui-badge ui-badge-warning',
  danger: 'ui-badge ui-badge-danger',
}

export function Badge({
  className,
  tone = 'default',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return <span className={cn(toneClasses[tone], className)} {...props} />
}

export function StatusDot({ tone = 'default' }: { tone?: BadgeTone }) {
  return <span className={cn('status-dot', tone !== 'default' && `status-dot-${tone}`)} />
}
