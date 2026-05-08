import 'server-only'

import { cache } from 'react'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { fetchBackendJson } from '@/lib/backend'

export const AUTH_COOKIE_NAME = 'hydro_auth_token'

export type SessionUser = {
  id: number
  username: string
  email?: string | null
  display_name?: string | null
  phone?: string | null
  is_active: boolean
  is_admin: boolean
  roles: string[]
  permissions: string[]
}

export const getSessionToken = cache(async () => {
  const cookieStore = await cookies()
  return cookieStore.get(AUTH_COOKIE_NAME)?.value || null
})

export const getSessionUser = cache(async (): Promise<SessionUser | null> => {
  const token = await getSessionToken()
  if (!token) {
    return null
  }

  try {
    const payload = await fetchBackendJson<{ user: SessionUser }>('/api/auth/me', { authToken: token })
    return payload.user
  } catch {
    return null
  }
})

export async function requirePermission(permission: string) {
  const user = await getSessionUser()
  if (!user) {
    redirect('/login')
  }
  if (!user.permissions.includes(permission)) {
    if (user.permissions.includes('dashboard:view')) redirect('/')
    if (user.permissions.includes('operations:view')) redirect('/operations')
    if (user.permissions.includes('assets:view')) redirect('/assets')
    if (user.permissions.includes('alerts:view')) redirect('/alerts')
    if (user.permissions.includes('reports:view')) redirect('/reports')
    if (user.permissions.includes('history:view')) redirect('/history')
    if (user.permissions.includes('chat:view')) redirect('/chat')
    if (user.permissions.includes('settings:view')) redirect('/settings')
    redirect('/login')
  }
  return user
}
