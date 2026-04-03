import { NextRequest } from 'next/server'
import { proxyCsv } from '@/lib/backend-proxy'

export async function GET(request: NextRequest) {
  return proxyCsv(request, '/api/reports/operations/export')
}
