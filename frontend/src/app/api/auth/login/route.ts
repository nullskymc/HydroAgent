import { NextRequest, NextResponse } from 'next/server'
import { AUTH_COOKIE_NAME } from '@/lib/auth'
import { fetchBackend } from '@/lib/backend'

function shouldUseSecureCookie(request: NextRequest) {
  const override = process.env.AUTH_COOKIE_SECURE
  if (override) return override === 'true'
  const forwardedProtocol = request.headers.get('x-forwarded-proto')
  return forwardedProtocol === 'https' || request.nextUrl.protocol === 'https:'
}

export async function POST(request: NextRequest) {
  const backendResponse = await fetchBackend('/api/auth/login', {
    method: 'POST',
    body: await request.text(),
  })
  if (!backendResponse.ok) {
    return new NextResponse(await backendResponse.text(), { status: backendResponse.status })
  }
  const payload = (await backendResponse.json()) as { token: string; user: Record<string, unknown> }

  const response = NextResponse.json({ user: payload.user })
  response.cookies.set(AUTH_COOKIE_NAME, payload.token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: shouldUseSecureCookie(request),
    path: '/',
    maxAge: 60 * 60 * 8,
  })
  return response
}
