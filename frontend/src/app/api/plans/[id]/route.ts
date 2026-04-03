import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

type Params = Promise<{ id: string }>

export async function GET(_: NextRequest, context: { params: Params }) {
  const { id } = await context.params
  return proxyJson(_, `/api/plans/${id}`)
}
