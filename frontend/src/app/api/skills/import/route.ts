import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

export async function POST(request: NextRequest) {
  return proxyJson(request, '/api/skills/import', { method: 'POST', body: await request.text() })
}
