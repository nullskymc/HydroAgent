import { NextRequest, NextResponse } from 'next/server'
import { AUTH_COOKIE_NAME } from '@/lib/auth'
import { fetchBackend } from '@/lib/backend'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(request: NextRequest) {
  const body = await request.text()
  const response = await fetchBackend('/api/chat', {
    method: 'POST',
    body,
    authToken: request.cookies.get(AUTH_COOKIE_NAME)?.value || null,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
  })

  if (!response.ok || !response.body) {
    return new NextResponse(await response.text(), { status: response.status })
  }

  const stream = new ReadableStream({
    async start(controller) {
      const reader = response.body!.getReader()
      const encoder = new TextEncoder()
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          if (value) {
            controller.enqueue(value)
          }
        }
        controller.close()
      } catch (error) {
        const detail = error instanceof Error ? error.message : '上游流式连接中断'
        const errorEvent = JSON.stringify({
          type: 'error',
          content: `流式连接中断：${detail}`,
        })
        controller.enqueue(encoder.encode(`data: ${errorEvent}\n\n`))
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`))
        controller.close()
      } finally {
        reader.releaseLock()
      }
    },
    cancel() {
      response.body?.cancel().catch(() => undefined)
    },
  })

  return new NextResponse(stream, {
    status: response.status,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  })
}
