import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

export async function GET(request: NextRequest) {
  return proxyJson(request, '/api/settings')
}

export async function PUT(request: NextRequest) {
  return proxyJson(request, '/api/settings', { method: 'PUT', body: await request.text() })
}
