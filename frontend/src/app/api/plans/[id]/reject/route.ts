import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/backend'

type Params = Promise<{ id: string }>

export async function POST(request: NextRequest, context: { params: Params }) {
  const { id } = await context.params
  const body = await request.text()
  const response = await fetchBackend(`/api/plans/${id}/reject`, {
    method: 'POST',
    body,
    headers: { 'Content-Type': 'application/json' },
  })
  return NextResponse.json(await response.json(), { status: response.status })
}
