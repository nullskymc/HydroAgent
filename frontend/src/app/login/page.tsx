import { LoginForm } from '@/components/login-form'
import { getSessionUser } from '@/lib/auth'
import { redirect } from 'next/navigation'

export default async function LoginPage() {
  const user = await getSessionUser()
  if (user) {
    redirect('/')
  }

  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="login-copy">
          <p className="eyebrow">HydroAgent</p>
          <h1>Secure Console</h1>
          <p>演示环境仅开放唯一管理员账号 admin / admin123</p>
        </div>
        <LoginForm />
      </section>
    </main>
  )
}
