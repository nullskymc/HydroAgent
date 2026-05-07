import { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

type BadgeTone = 'default' | 'success' | 'warning' | 'danger'

const toneClasses: Record<BadgeTone, string> = {
  default: 'border-slate-200 bg-slate-50 text-slate-600',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  danger: 'border-rose-200 bg-rose-50 text-rose-700',
}

export function Badge({
  className,
  tone = 'default',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[0.68rem] font-semibold tracking-normal',
        toneClasses[tone],
        className,
      )}
      {...props}
    />
  )
}

export function StatusDot({ tone = 'default' }: { tone?: BadgeTone }) {
  const dotClasses: Record<BadgeTone, string> = {
    default: 'bg-slate-300',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-rose-500',
  }
  return <span className={cn('inline-block size-2 rounded-full', dotClasses[tone])} />
}
