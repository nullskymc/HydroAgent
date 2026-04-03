'use client'

import { FormEvent, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function LoginForm() {
  const router = useRouter()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    startTransition(async () => {
      setError(null)
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })

      if (!response.ok) {
        setError(await response.text())
        return
      }

      router.push('/')
      router.refresh()
    })
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <label className="login-field">
        <span>用户名</span>
        <Input value={username} onChange={(event) => setUsername(event.target.value)} />
      </label>
      <label className="login-field">
        <span>密码</span>
        <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      {error ? <div className="login-error">{error}</div> : null}
      <Button type="submit" disabled={isPending}>
        {isPending ? '登录中...' : '进入后台'}
      </Button>
    </form>
  )
}
