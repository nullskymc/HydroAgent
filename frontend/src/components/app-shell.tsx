import Link from 'next/link'
import { Activity, BarChart3, Bell, BookOpenText, Bot, Boxes, History, Radar, Settings, Users } from 'lucide-react'
import { getSessionUser } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { LogoutButton } from '@/components/logout-button'

const navItems = [
  { href: '/', label: '运营总览', icon: Radar, permission: 'dashboard:view' },
  { href: '/visualization', label: '数据大屏', icon: Activity, permission: 'dashboard:view' },
  { href: '/chat', label: '智能对话', icon: Bot, permission: 'chat:view' },
  { href: '/operations', label: '运营中心', icon: BarChart3, permission: 'operations:view' },
  { href: '/assets', label: '资产中心', icon: Boxes, permission: 'assets:view' },
  { href: '/knowledge', label: '知识库', icon: BookOpenText, permission: 'knowledge:view' },
  { href: '/alerts', label: '告警中心', icon: Bell, permission: 'alerts:view' },
  { href: '/users', label: '用户与角色', icon: Users, permission: 'users:view' },
  { href: '/reports', label: '报表中心', icon: BarChart3, permission: 'reports:view' },
  { href: '/history', label: '审计记录', icon: History, permission: 'history:view' },
  { href: '/settings', label: '系统设置', icon: Settings, permission: 'settings:view' },
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

function ShellNav({ currentPath, permissions }: { currentPath: string; permissions: string[] }) {
  const visibleNavItems = navItems.filter((item) => !item.permission || permissions.includes(item.permission))

  return (
    <nav className="nav-list nav-list-horizontal">
      {visibleNavItems.map((item) => {
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

export async function AppShell({ children, currentPath }: { children: React.ReactNode; currentPath: string }) {
  const user = await getSessionUser()
  return (
    <div className="app-frame">
      <header className="shell-header">
        <div className="shell-topbar">
          <BrandBlock />
          <ShellNav currentPath={currentPath} permissions={user?.permissions || []} />
          <div className="shell-userbox">
            <div className="shell-usercopy">
              <strong>{user?.display_name || user?.username || '未登录'}</strong>
              <span>{user?.roles?.join(' / ') || 'guest'}</span>
            </div>
            {user ? <LogoutButton /> : null}
          </div>
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

export async function ChatShell({ children, currentPath }: { children: React.ReactNode; currentPath: string }) {
  const user = await getSessionUser()
  return (
    <div className="chat-app-shell">
      <header className="shell-header shell-header-compact">
        <div className="shell-topbar chat-app-topbar">
          <BrandBlock compact />
          <ShellNav currentPath={currentPath} permissions={user?.permissions || []} />
        </div>
      </header>
      <main className="chat-app-main">{children}</main>
    </div>
  )
}
