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
          <h1>运营后台登录</h1>
          <p>默认演示账号：admin / admin123。也可使用 manager、operator、viewer、auditor 对应角色账号。</p>
        </div>
        <LoginForm />
      </section>
    </main>
  )
}
