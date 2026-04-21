'use client'

import { motion } from 'framer-motion'
import { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'

type StatTone = 'default' | 'blue' | 'success' | 'warning' | 'danger'

const toneClasses: Record<StatTone, string> = {
  default: 'text-slate-500 bg-slate-50',
  blue: 'text-[#0052FF] bg-blue-50',
  success: 'text-emerald-700 bg-emerald-50',
  warning: 'text-amber-700 bg-amber-50',
  danger: 'text-rose-700 bg-rose-50',
}

export function StatCard({
  label,
  value,
  unit,
  description,
  icon: Icon,
  tone = 'default',
  isLoading = false,
  className,
}: {
  label: string
  value: string | number
  unit?: string
  description?: string
  icon?: LucideIcon
  tone?: StatTone
  isLoading?: boolean
  className?: string
}) {
  return (
    <motion.section
      whileHover={{ y: -2 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className={cn('rounded-lg border border-slate-200/80 bg-white p-4 shadow-sm transition-shadow hover:shadow-md', className)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[0.64rem] font-semibold uppercase tracking-widest text-slate-400">{label}</p>
          {isLoading ? (
            <Skeleton className="mt-3 h-8 w-24" />
          ) : (
            <div className="mt-2 flex items-baseline gap-1">
              <strong className="font-sans text-2xl font-semibold tracking-normal text-slate-950">{value}</strong>
              {unit ? <span className="text-xs font-medium text-slate-500">{unit}</span> : null}
            </div>
          )}
          {description ? <p className="mt-1.5 text-xs leading-5 text-slate-500">{description}</p> : null}
        </div>
        {Icon ? (
          <div className={cn('flex size-8 items-center justify-center rounded-md', toneClasses[tone])}>
            <Icon className="size-4" aria-hidden="true" />
          </div>
        ) : null}
      </div>
    </motion.section>
  )
}
