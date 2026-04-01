import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'HydroAgent 控制台',
  description: '面向智慧灌溉系统的 Next.js + Vercel 前端控制台',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}
