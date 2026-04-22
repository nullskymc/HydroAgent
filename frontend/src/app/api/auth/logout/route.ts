import { NextRequest } from 'next/server'
import { AUTH_COOKIE_NAME } from '@/lib/auth'
import { proxyJson } from '@/lib/backend-proxy'

export async function POST(request: NextRequest) {
  const response = await proxyJson(request, '/api/auth/logout', { method: 'POST' })
  response.cookies.delete(AUTH_COOKIE_NAME)
  return response
}
