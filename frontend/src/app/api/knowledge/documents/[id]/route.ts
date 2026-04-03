import { NextRequest } from 'next/server'
import { proxyJson } from '@/lib/backend-proxy'

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(request, `/api/knowledge/documents/${id}`)
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(request, `/api/knowledge/documents/${id}`, { method: 'DELETE' })
}
