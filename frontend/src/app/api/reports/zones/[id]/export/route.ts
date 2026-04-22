import { NextRequest } from 'next/server'
import { proxyCsv } from '@/lib/backend-proxy'

type Params = Promise<{ id: string }>

export async function GET(request: NextRequest, context: { params: Params }) {
  const { id } = await context.params
  return proxyCsv(request, `/api/reports/zones/${id}/export`)
}
