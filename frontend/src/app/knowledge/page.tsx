import { AppShell } from '@/components/app-shell'
import { KnowledgeConsole } from '@/components/knowledge-console'
import { requirePermission } from '@/lib/auth'
import { getKnowledgeDocumentDetail, getKnowledgeDocuments } from '@/lib/server-data'
import { KnowledgeDocumentDetail, KnowledgeDocumentList } from '@/lib/types'

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams?: Promise<{ page?: string; document?: string; chunkPage?: string }>
}) {
  await requirePermission('knowledge:view')
  const resolvedSearchParams = (await searchParams) || {}
  const page = Math.max(1, Number(resolvedSearchParams.page || '1') || 1)
  const chunkPage = Math.max(1, Number(resolvedSearchParams.chunkPage || '1') || 1)

  const initialList: KnowledgeDocumentList = await getKnowledgeDocuments(page, 10).catch(() => ({
    documents: [],
    pagination: {
      page,
      page_size: 10,
      total: 0,
      total_pages: 1,
      has_prev: false,
      has_next: false,
    },
  }))

  const selectedDocumentId =
    resolvedSearchParams.document && initialList.documents.some((item) => item.document_id === resolvedSearchParams.document)
      ? resolvedSearchParams.document
      : initialList.documents[0]?.document_id

  const initialDetail: KnowledgeDocumentDetail | null = selectedDocumentId
    ? await getKnowledgeDocumentDetail(selectedDocumentId, chunkPage, 8).catch(() => null)
    : null

  return (
    <AppShell currentPath="/knowledge">
      <KnowledgeConsole initialList={initialList} initialDetail={initialDetail} />
    </AppShell>
  )
}
