import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

export async function GET(request: NextRequest) {
  return proxyJson(request, '/api/users')
}

export async function POST(request: NextRequest) {
  return proxyJson(request, '/api/users', { method: 'POST', body: await request.text() })
}
