import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

type Params = Promise<{ id: string }>

export async function PATCH(request: NextRequest, context: { params: Params }) {
  const { id } = await context.params
  return proxyJson(request, `/api/assets/actuators/${id}`, { method: 'PATCH', body: await request.text() })
}
