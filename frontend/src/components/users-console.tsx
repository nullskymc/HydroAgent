'use client'

import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet, apiSend } from '@/lib/api-client'
import { Role, UserProfile } from '@/lib/types'

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

  function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    createMutation.mutate()
  }

  return (
    <div className="admin-grid admin-grid-2">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4">
          <SectionBadge label="Create User" />
          <form className="admin-form" onSubmit={createUser}>
            <Input placeholder="用户名" value={draft.username} onChange={(event) => setDraft((current) => ({ ...current, username: event.target.value }))} />
            <Input placeholder="显示名" value={draft.display_name} onChange={(event) => setDraft((current) => ({ ...current, display_name: event.target.value }))} />
            <Input placeholder="密码" type="password" value={draft.password} onChange={(event) => setDraft((current) => ({ ...current, password: event.target.value }))} />
            <Input placeholder="角色，逗号分隔" value={draft.role_keys} onChange={(event) => setDraft((current) => ({ ...current, role_keys: event.target.value }))} />
            <Button type="submit" disabled={createMutation.isPending}>创建账号</Button>
          </form>
          <div className="admin-hint">可用角色：{roles.map((role) => role.role_key).join(' / ')}</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <SectionBadge label="Users" />
            <Badge>{usersQuery.data.length}</Badge>
          </div>
          {usersQuery.data.length === 0 ? (
            <EmptyState title="暂无用户" description="当前还没有可管理用户。" />
          ) : (
            <div className="admin-list">
              {usersQuery.data.map((user) => (
                <div key={user.id} className="admin-list-item">
                  <div>
                    <strong>{user.display_name || user.username}</strong>
                    <p>{user.username} · {user.roles.join(', ')}</p>
                    <Badge tone={user.is_active ? 'success' : 'default'}>{user.is_active ? '启用' : '停用'}</Badge>
                  </div>
                  <Button size="sm" variant={user.is_active ? 'secondary' : 'primary'} disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate(user)}>
                    {user.is_active ? '停用' : '启用'}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
