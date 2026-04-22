import { NextResponse } from 'next/server'
import { getHistoryData } from '@/lib/server-data'

export async function GET() {
  const data = await getHistoryData()
  return NextResponse.json(data)
}
