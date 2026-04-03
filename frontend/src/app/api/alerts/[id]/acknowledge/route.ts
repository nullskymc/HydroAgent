import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

type Params = Promise<{ id: string }>

export async function POST(request: NextRequest, context: { params: Params }) {
  const { id } = await context.params
  return proxyJson(request, `/api/alerts/${id}/acknowledge`, { method: 'POST', body: await request.text() })
}
