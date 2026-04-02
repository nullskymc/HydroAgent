import { NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/backend'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const search = url.searchParams.toString()
  const response = await fetchBackend(`/api/tool-traces${search ? `?${search}` : ''}`)
  return NextResponse.json(await response.json(), { status: response.status })
}
