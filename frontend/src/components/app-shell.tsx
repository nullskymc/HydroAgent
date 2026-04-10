import Link from 'next/link'
import type { LucideIcon } from 'lucide-react'
import { Activity, BarChart3, Bell, BookOpenText, Bot, Boxes, History, Radar, Settings, Users } from 'lucide-react'
import { getSessionUser } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { LogoutButton } from '@/components/logout-button'

type NavGroup = 'primary' | 'secondary'

type NavItem = {
  href: string
  label: string
  icon: LucideIcon
  permission: string
  group: NavGroup
}

const navItems: NavItem[] = [
  { href: '/', label: '总览', icon: Radar, permission: 'dashboard:view', group: 'primary' },
  { href: '/operations', label: '调度', icon: BarChart3, permission: 'operations:view', group: 'primary' },
  { href: '/chat', label: '助手', icon: Bot, permission: 'chat:view', group: 'primary' },
  { href: '/assets', label: '资产', icon: Boxes, permission: 'assets:view', group: 'primary' },
  { href: '/alerts', label: '告警', icon: Bell, permission: 'alerts:view', group: 'primary' },
  { href: '/visualization', label: '数据大屏', icon: Activity, permission: 'dashboard:view', group: 'secondary' },
  { href: '/knowledge', label: '知识库', icon: BookOpenText, permission: 'knowledge:view', group: 'secondary' },
  { href: '/reports', label: '报表', icon: BarChart3, permission: 'reports:view', group: 'secondary' },
  { href: '/history', label: '审计', icon: History, permission: 'history:view', group: 'secondary' },
  { href: '/users', label: '用户', icon: Users, permission: 'users:view', group: 'secondary' },
  { href: '/settings', label: '设置', icon: Settings, permission: 'settings:view', group: 'secondary' },
]

function isNavItemVisible(item: NavItem, permissions: string[]) {
  return permissions.includes(item.permission)
}

// 统一在这里完成权限过滤和当前页解析，避免头部组件同时承担业务判断与展示职责。
function buildNavigationModel(currentPath: string, permissions: string[]) {
  const visibleNavItems = navItems.filter((item) => isNavItemVisible(item, permissions))
  const fallbackItem = visibleNavItems[0] || navItems[0]

  return {
    currentItem: visibleNavItems.find((item) => item.href === currentPath) || fallbackItem,
    primaryItems: visibleNavItems.filter((item) => item.group === 'primary'),
    secondaryItems: visibleNavItems.filter((item) => item.group === 'secondary'),
  }
}

function BrandBlock({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className={cn('brand-block', compact && 'brand-block-compact')}>
      <div className="brand-mark">H</div>
      <div>
        <p className="eyebrow">HydroAgent</p>
        <h1>智能灌溉控制台</h1>
      </div>
    </Link>
  )
}

function ShellNav({
  items,
  currentPath,
  title,
}: {
  items: NavItem[]
  currentPath: string
  title: string
}) {
  if (items.length === 0) {
    return null
  }

  return (
    <section className="shell-nav-section" aria-label={title}>
      <p className="shell-nav-section-title">{title}</p>
      <nav className="shell-nav-list">
        {items.map((item) => {
          const Icon = item.icon
          const active = currentPath === item.href
          return (
            <Link key={item.href} href={item.href} className={cn('shell-nav-link', active && 'is-active')}>
              <span className="shell-nav-link-main">
                <Icon size={16} />
                <span>{item.label}</span>
              </span>
            </Link>
          )
        })}
      </nav>
    </section>
  )
}

function ShellSidebar({
  currentPath,
  navigation,
  user,
  compact = false,
}: {
  currentPath: string
  navigation: ReturnType<typeof buildNavigationModel>
  user: Awaited<ReturnType<typeof getSessionUser>>
  compact?: boolean
}) {
  return (
    <aside className={cn('shell-sidebar', compact && 'shell-sidebar-compact')}>
      <div className="shell-sidebar-surface">
        <div className="shell-sidebar-brand">
          <BrandBlock compact={compact} />
          <p className="shell-sidebar-note">围绕灌溉计划、执行审批和风险监控组织导航，避免头部信息拥挤。</p>
        </div>

        <div className="shell-sidebar-navstack">
          <ShellNav items={navigation.primaryItems} currentPath={currentPath} title="核心工作台" />
          <ShellNav items={navigation.secondaryItems} currentPath={currentPath} title="系统配置" />
        </div>

        <div className="shell-sidebar-usercard">
          <div className="shell-usercopy">
            <span className="shell-user-role">{user?.roles?.join(' / ') || 'guest'}</span>
            <strong>{user?.display_name || user?.username || '未登录'}</strong>
          </div>
          {user ? <LogoutButton /> : null}
        </div>
      </div>
    </aside>
  )
}

export async function AppShell({ children, currentPath }: { children: React.ReactNode; currentPath: string }) {
  const user = await getSessionUser()
  const navigation = buildNavigationModel(currentPath, user?.permissions || [])

  return (
    <div className="app-frame app-shell-layout">
      <ShellSidebar currentPath={currentPath} navigation={navigation} user={user} />
      <main className="page-panel shell-page-panel">{children}</main>
    </div>
  )
}

export async function ChatShell({ children, currentPath }: { children: React.ReactNode; currentPath: string }) {
  const user = await getSessionUser()
  const navigation = buildNavigationModel(currentPath, user?.permissions || [])

  return (
    <div className="chat-app-shell app-shell-layout">
      <ShellSidebar currentPath={currentPath} navigation={navigation} user={user} compact />
      <main className="chat-app-main shell-page-panel">{children}</main>
    </div>
  )
}
