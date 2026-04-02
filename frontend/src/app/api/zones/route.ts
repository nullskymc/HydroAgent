import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/backend'

export async function GET(request: NextRequest) {
  const response = await fetchBackend('/api/zones', {
    searchParams: request.nextUrl.searchParams,
  })
  return NextResponse.json(await response.json(), { status: response.status })
}
