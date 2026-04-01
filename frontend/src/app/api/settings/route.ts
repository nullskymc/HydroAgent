import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/backend'

export async function GET() {
  const response = await fetchBackend('/api/settings')
  return NextResponse.json(await response.json(), { status: response.status })
}

export async function PUT(request: NextRequest) {
  const body = await request.text()
  const response = await fetchBackend('/api/settings', {
    method: 'PUT',
    body,
    headers: { 'Content-Type': 'application/json' },
  })

  return NextResponse.json(await response.json(), { status: response.status })
}
