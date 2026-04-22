import { NextResponse } from 'next/server'
import { getDashboardData } from '@/lib/server-data'

export async function GET() {
  const data = await getDashboardData()
  return NextResponse.json(data, { status: data.backendReachable ? 200 : 503 })
}
