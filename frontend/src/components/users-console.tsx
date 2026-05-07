'use client'

import { FormEvent, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge, StatusDot } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet, apiSend } from '@/lib/api-client'
import { Role, UserProfile } from '@/lib/types'
import { formatDateTime } from '@/lib/utils'

export function UsersConsole({ initialUsers, roles }: { initialUsers: UserProfile[]; roles: Role[] }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState({ username: '', password: 'viewer123', display_name: '', role_keys: 'viewer' })
  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: () => apiGet<{ users: UserProfile[] }>('/api/users').then((payload) => payload.users || []),
    initialData: initialUsers,
    refetchInterval: 20_000,
  })
  const createMutation = useMutation({
    mutationFn: () =>
      apiSend('/api/users', 'POST', {
        username: draft.username,
        password: draft.password,
        display_name: draft.display_name,
        role_keys: draft.role_keys.split(',').map((item) => item.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      setDraft({ username: '', password: 'viewer123', display_name: '', role_keys: 'viewer' })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
  const toggleMutation = useMutation({
    mutationFn: (user: UserProfile) => apiSend(`/api/users/${user.id}`, 'PATCH', { is_active: !user.is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  const roleNames = useMemo(() => roles.map((role) => role.role_key).join(' / '), [roles])
  const activeCount = usersQuery.data.filter((user) => user.is_active).length
  const adminCount = usersQuery.data.filter((user) => user.is_admin).length

  function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    createMutation.mutate()
  }

  return (
    <div className="page-stack">
      <section className="console-telemetry-bar">
        <div className="console-telemetry-title">
          <p className="eyebrow">Access Control</p>
          <h2>用户与权限</h2>
        </div>
        <div className="console-telemetry-stream">
          {[
            { label: '用户', value: usersQuery.data.length },
            { label: '启用', value: activeCount },
            { label: '管理员', value: adminCount },
            { label: '角色', value: roles.length },
          ].map((item) => (
            <div key={item.label} className="console-telemetry-item">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
        <div className="console-telemetry-meta">
          <span>{usersQuery.isFetching ? 'Syncing' : 'RBAC'}</span>
          <strong>{roleNames || 'No roles'}</strong>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <section className="surface-panel flex flex-col gap-3">
          <div>
            <SectionBadge label="Create User" />
            <h2 className="m-0 mt-2 text-base font-semibold text-slate-950">创建账号</h2>
            <p className="m-0 mt-1 text-xs leading-5 text-slate-500">创建后立即纳入权限表，默认使用逗号分隔角色。</p>
          </div>
          <form className="admin-form" onSubmit={createUser}>
            <Input placeholder="用户名" value={draft.username} onChange={(event) => setDraft((current) => ({ ...current, username: event.target.value }))} />
            <Input placeholder="显示名" value={draft.display_name} onChange={(event) => setDraft((current) => ({ ...current, display_name: event.target.value }))} />
            <Input placeholder="密码" type="password" value={draft.password} onChange={(event) => setDraft((current) => ({ ...current, password: event.target.value }))} />
            <Input placeholder="角色，逗号分隔" value={draft.role_keys} onChange={(event) => setDraft((current) => ({ ...current, role_keys: event.target.value }))} />
            <Button type="submit" disabled={createMutation.isPending || !draft.username.trim() || !draft.password.trim()}>
              {createMutation.isPending ? '创建中' : '创建账号'}
            </Button>
          </form>
          <div className="rounded-md bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500">可用角色：{roleNames || '--'}</div>
        </section>

        <section className="surface-panel flex min-w-0 flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <SectionBadge label="Users" />
              <h2 className="m-0 mt-2 text-base font-semibold text-slate-950">账号列表</h2>
            </div>
            <Badge>{usersQuery.data.length} 项</Badge>
          </div>

          {usersQuery.data.length === 0 ? (
            <EmptyState title="暂无用户" description="当前还没有可管理用户。" />
          ) : (
            <div className="data-table-shell">
              <table className="min-w-[820px] w-full border-collapse text-sm">
                <thead className="bg-slate-50 text-left font-mono text-[0.64rem] font-semibold tracking-normal text-slate-400">
                  <tr>
                    <th className="h-9 border-b border-slate-100 px-3">账号</th>
                    <th className="h-9 border-b border-slate-100 px-3">角色</th>
                    <th className="h-9 border-b border-slate-100 px-3">状态</th>
                    <th className="h-9 border-b border-slate-100 px-3">最近登录</th>
                    <th className="h-9 border-b border-slate-100 px-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {usersQuery.data.map((user) => (
                    <tr key={user.id} className="border-b border-slate-100 last:border-b-0 hover:bg-blue-50/40">
                      <td className="h-11 px-3">
                        <strong className="block truncate text-sm font-semibold text-slate-950">{user.display_name || user.username}</strong>
                        <span className="block truncate text-xs text-slate-500">{user.username}</span>
                      </td>
                      <td className="h-11 px-3">
                        <div className="flex flex-wrap gap-1.5">
                          {user.roles.map((role) => (
                            <Badge key={`${user.id}-${role}`}>{role}</Badge>
                          ))}
                        </div>
                      </td>
                      <td className="h-11 px-3">
                        <div className="flex flex-wrap gap-1.5">
                          <Badge tone={user.is_active ? 'success' : 'default'}>
                            <StatusDot tone={user.is_active ? 'success' : 'default'} />
                            {user.is_active ? '启用' : '停用'}
                          </Badge>
                          {user.is_admin ? <Badge tone="warning">管理员</Badge> : null}
                        </div>
                      </td>
                      <td className="h-11 whitespace-nowrap px-3 text-xs text-slate-500">{formatDateTime(user.last_login)}</td>
                      <td className="h-11 px-3 text-right">
                        <Button size="sm" variant={user.is_active ? 'secondary' : 'primary'} disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate(user)}>
                          {user.is_active ? '停用' : '启用'}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
