import Link from 'next/link'
import { Bot, History, Radar, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/', label: '智能体中枢', icon: Radar },
  { href: '/chat', label: '智能对话', icon: Bot },
  { href: '/history', label: '审计记录', icon: History },
  { href: '/settings', label: '系统设置', icon: Settings },
]

function BrandBlock({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className={cn('brand-block', compact && 'brand-block-compact')}>
      <div className="brand-mark">H</div>
      <div>
        <p className="eyebrow">HydroAgent</p>
        <h1>水利灌溉智能体系统</h1>
      </div>
    </Link>
  )
}

function ShellNav({ currentPath }: { currentPath: string }) {
  return (
    <nav className="nav-list nav-list-horizontal">
      {navItems.map((item) => {
        const Icon = item.icon
        const active = currentPath === item.href
        return (
          <Link key={item.href} href={item.href} className={cn('nav-link', active && 'nav-link-active')}>
            <div className="nav-link-main">
              <Icon size={16} />
              <span>{item.label}</span>
            </div>
          </Link>
        )
      })}
    </nav>
  )
}

export function AppShell({ children, currentPath }: { children: React.ReactNode; currentPath: string }) {
  return (
    <div className="app-frame">
      <header className="shell-header">
        <div className="shell-topbar">
          <BrandBlock />
          <ShellNav currentPath={currentPath} />
        </div>
      </header>

      <main className="page-panel">
        <div className="workspace-topbar">
          <span>Smart Irrigation / Operation Center</span>
          <span className="workspace-topbar-meta">实时运行中枢</span>
        </div>
        {children}
      </main>
    </div>
  )
}

export function ChatShell({ children, currentPath }: { children: React.ReactNode; currentPath: string }) {
  return (
    <div className="chat-app-shell">
      <header className="shell-header shell-header-compact">
        <div className="shell-topbar chat-app-topbar">
          <BrandBlock compact />
          <ShellNav currentPath={currentPath} />
        </div>
      </header>
      <main className="chat-app-main">{children}</main>
    </div>
  )
}
