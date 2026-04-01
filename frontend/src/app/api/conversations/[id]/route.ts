import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/backend'

type Params = Promise<{ id: string }>

export async function GET(_: NextRequest, context: { params: Params }) {
  const { id } = await context.params
  const response = await fetchBackend(`/api/conversations/${id}`)
  return NextResponse.json(await response.json(), { status: response.status })
}

export async function DELETE(_: NextRequest, context: { params: Params }) {
  const { id } = await context.params
  const response = await fetchBackend(`/api/conversations/${id}`, { method: 'DELETE' })
  return NextResponse.json(await response.json(), { status: response.status })
}
