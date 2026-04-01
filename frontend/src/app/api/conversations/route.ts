import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/backend'

export async function GET() {
  const response = await fetchBackend('/api/conversations')
  return NextResponse.json(await response.json(), { status: response.status })
}

export async function POST(request: NextRequest) {
  const body = await request.text()
  const response = await fetchBackend('/api/conversations', {
    method: 'POST',
    body,
    headers: { 'Content-Type': 'application/json' },
  })

  return NextResponse.json(await response.json(), { status: response.status })
}
