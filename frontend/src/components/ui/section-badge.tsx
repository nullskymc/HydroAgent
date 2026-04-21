'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

export function SectionBadge({ label, className }: { label: string; className?: string }) {
  return (
    <div className={cn('inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[#0052FF]', className)}>
      <motion.span
        className="size-2 rounded-full bg-[#0052FF]"
        animate={{ scale: [1, 1.45, 1], opacity: [0.55, 1, 0.55] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
      />
      <span className="font-mono text-[0.64rem] font-semibold uppercase tracking-widest">{label}</span>
    </div>
  )
}
