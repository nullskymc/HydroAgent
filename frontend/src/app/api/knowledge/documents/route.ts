import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

export async function GET(request: NextRequest) {
  return proxyJson(request, '/api/knowledge/documents')
}

export async function POST(request: NextRequest) {
  return proxyJson(request, '/api/knowledge/documents', { method: 'POST', body: await request.text() })
}
