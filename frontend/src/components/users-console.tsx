'use client'

import { FormEvent, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Role, UserProfile } from '@/lib/types'

export function UsersConsole({ initialUsers, roles }: { initialUsers: UserProfile[]; roles: Role[] }) {
  const [users, setUsers] = useState(initialUsers)
  const [draft, setDraft] = useState({ username: '', password: 'viewer123', display_name: '', role_keys: 'viewer' })

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const response = await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: draft.username,
        password: draft.password,
        display_name: draft.display_name,
        role_keys: draft.role_keys.split(',').map((item) => item.trim()).filter(Boolean),
      }),
    })
    if (!response.ok) return
    const payload = await response.json()
    setUsers((current) => [...current, payload.user])
    setDraft({ username: '', password: 'viewer123', display_name: '', role_keys: 'viewer' })
  }

  async function toggleUser(user: UserProfile) {
    const response = await fetch(`/api/users/${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !user.is_active }),
    })
    if (!response.ok) return
    const payload = await response.json()
    setUsers((current) => current.map((item) => (item.id === user.id ? payload.user : item)))
  }

  return (
    <div className="admin-grid admin-grid-2">
      <Card>
        <CardHeader><CardTitle>创建用户</CardTitle></CardHeader>
        <CardContent>
          <form className="admin-form" onSubmit={createUser}>
            <Input placeholder="用户名" value={draft.username} onChange={(event) => setDraft((current) => ({ ...current, username: event.target.value }))} />
            <Input placeholder="显示名" value={draft.display_name} onChange={(event) => setDraft((current) => ({ ...current, display_name: event.target.value }))} />
            <Input placeholder="密码" type="password" value={draft.password} onChange={(event) => setDraft((current) => ({ ...current, password: event.target.value }))} />
            <Input placeholder="角色，逗号分隔" value={draft.role_keys} onChange={(event) => setDraft((current) => ({ ...current, role_keys: event.target.value }))} />
            <Button type="submit">创建账号</Button>
          </form>
          <div className="admin-hint">可用角色：{roles.map((role) => role.role_key).join(' / ')}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>用户列表</CardTitle></CardHeader>
        <CardContent className="admin-list">
          {users.map((user) => (
            <div key={user.id} className="admin-list-item">
              <div>
                <strong>{user.display_name || user.username}</strong>
                <p>{user.username} · {user.roles.join(', ')}</p>
              </div>
              <Button size="sm" variant={user.is_active ? 'secondary' : 'primary'} onClick={() => toggleUser(user)}>
                {user.is_active ? '停用' : '启用'}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
