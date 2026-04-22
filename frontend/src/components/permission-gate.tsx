import { ReactNode } from 'react'
import { UserProfile } from '@/lib/types'

export function PermissionGate({
  user,
  permission,
  fallback = null,
  children,
}: {
  user: UserProfile | null
  permission: string
  fallback?: ReactNode
  children: ReactNode
}) {
  if (!user || !user.permissions.includes(permission)) {
    return <>{fallback}</>
  }
  return <>{children}</>
}
