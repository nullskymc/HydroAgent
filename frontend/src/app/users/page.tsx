import { AppShell } from '@/components/app-shell'
import { UsersConsole } from '@/components/users-console'
import { requirePermission } from '@/lib/auth'
import { getUserAdminData } from '@/lib/server-data'

export default async function UsersPage() {
  await requirePermission('users:view')
  const data = await getUserAdminData()

  return (
    <AppShell currentPath="/users">
      <div className="page-stack">
        <UsersConsole initialUsers={data.users} roles={data.roles} />
      </div>
    </AppShell>
  )
}
