import { NextRequest, NextResponse } from 'next/server'
import { AUTH_COOKIE_NAME } from '@/lib/auth'
import { fetchBackend } from '@/lib/backend'

function getAuthToken(request: NextRequest) {
  return request.cookies.get(AUTH_COOKIE_NAME)?.value || null
}

export async function proxyJson(request: NextRequest, path: string, init?: { method?: string; body?: string }) {
  const response = await fetchBackend(path, {
    method: init?.method || request.method,
    body: init?.body,
    searchParams: request.nextUrl.searchParams,
    authToken: getAuthToken(request),
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return NextResponse.json(await response.json(), { status: response.status })
  }

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { 'Content-Type': contentType || 'text/plain; charset=utf-8' },
  })
}

export async function proxyCsv(request: NextRequest, path: string) {
  const response = await fetchBackend(path, {
    method: request.method,
    searchParams: request.nextUrl.searchParams,
    authToken: getAuthToken(request),
  })
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') || 'text/csv; charset=utf-8',
      'Content-Disposition': response.headers.get('content-disposition') || 'attachment',
    },
  })
}
