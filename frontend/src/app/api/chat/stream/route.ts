import { NextRequest, NextResponse } from 'next/server'
import { fetchBackend } from '@/lib/backend'

export async function POST(request: NextRequest) {
  const body = await request.text()
  const response = await fetchBackend('/api/chat', {
    method: 'POST',
    body,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
  })

  if (!response.ok || !response.body) {
    return new NextResponse(await response.text(), { status: response.status })
  }

  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  })
}
