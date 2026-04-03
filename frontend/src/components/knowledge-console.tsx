'use client'

import { useMemo, useState, useTransition } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { ConsoleEmptyState, ConsoleSectionHeader } from '@/components/console-primitives'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { KnowledgeDocumentDetail, KnowledgeDocumentList } from '@/lib/types'
import { cn, formatDateTime } from '@/lib/utils'

function buildHref(params: URLSearchParams | null, updates: Record<string, string | null>) {
  const next = new URLSearchParams(params?.toString() || '')
  for (const [key, value] of Object.entries(updates)) {
    if (value === null) {
      next.delete(key)
    } else {
      next.set(key, value)
    }
  }
  const query = next.toString()
  return query ? `/knowledge?${query}` : '/knowledge'
}

export function KnowledgeConsole({
  initialList,
  initialDetail,
}: {
  initialList: KnowledgeDocumentList
  initialDetail: KnowledgeDocumentDetail | null
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [title, setTitle] = useState('')
  const [sourceUri, setSourceUri] = useState('')
  const [content, setContent] = useState('')
  const [feedback, setFeedback] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const activeDocumentId = initialDetail?.document.document_id || ''
  const telemetry = useMemo(
    () => [
      { label: '当前页文档', value: `${initialList.documents.length}` },
      { label: '总文档数', value: `${initialList.pagination.total}` },
      { label: '当前切片', value: `${initialDetail?.pagination.total || 0}` },
      { label: '默认召回', value: `${initialDetail ? '已接入聊天检索' : '等待文档入库'}` },
    ],
    [initialDetail, initialList.documents.length, initialList.pagination.total],
  )

  function navigate(updates: Record<string, string | null>) {
    router.push(buildHref(searchParams, updates))
  }

  function submitDocument() {
    startTransition(async () => {
      setFeedback(null)
      const response = await fetch('/api/knowledge/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          source_uri: sourceUri || null,
          content,
        }),
      })

      const payload = (await response.json().catch(() => null)) as
        | { detail?: string; created?: boolean; document?: { document_id: string } }
        | null

      if (!response.ok) {
        setFeedback(payload?.detail || '知识文档写入失败。')
        return
      }

      setTitle('')
      setSourceUri('')
      setContent('')
      const documentId = payload?.document?.document_id
      setFeedback(payload?.created ? '知识文档已写入并建立向量索引。' : '检测到重复内容，已复用现有知识文档。')
      router.push(documentId ? `/knowledge?document=${documentId}` : '/knowledge')
      router.refresh()
    })
  }

  function removeDocument(documentId: string) {
    startTransition(async () => {
      setFeedback(null)
      const response = await fetch(`/api/knowledge/documents/${documentId}`, {
        method: 'DELETE',
      })
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      if (!response.ok) {
        setFeedback(payload?.detail || '删除知识文档失败。')
        return
      }

      const nextDocument = initialList.documents.find((item) => item.document_id !== documentId)?.document_id || null
      setFeedback('知识文档已删除，向量索引已同步清理。')
      navigate({ document: nextDocument, chunkPage: null })
      router.refresh()
    })
  }

  return (
    <div className="page-stack knowledge-console-page">
      <section className="console-telemetry-bar knowledge-console-bar">
        <div className="console-telemetry-title">
          <p className="eyebrow">Embeddings / Knowledge Base</p>
          <h2>知识库控制台</h2>
        </div>
        <div className="console-telemetry-stream audit-console-stream">
          {telemetry.map((item) => (
            <div key={item.label} className="console-telemetry-item">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
        <div className="console-telemetry-meta">
          <span>RAG Ready</span>
          <strong>Persistent Chroma / OpenAI Embeddings</strong>
        </div>
      </section>

      <section className="console-section knowledge-ingest-panel">
        <ConsoleSectionHeader eyebrow="录入" title="新建知识文档" meta={<span className="console-plain-meta">纯文本直写入库</span>} />
        <div className="knowledge-ingest-grid">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="文档标题，例如：阀门维护 SOP" />
          <Input value={sourceUri} onChange={(event) => setSourceUri(event.target.value)} placeholder="来源地址，可选" />
        </div>
        <Textarea
          rows={8}
          value={content}
          onChange={(event) => setContent(event.target.value)}
          placeholder="粘贴需要纳入知识库的手册、SOP、设备说明或业务规则文本。"
        />
        <div className="knowledge-ingest-actions">
          <Button disabled={isPending || !title.trim() || !content.trim()} onClick={submitDocument}>
            {isPending ? '写入中...' : '写入知识库'}
          </Button>
          {feedback ? <span className="settings-save-message">{feedback}</span> : null}
        </div>
      </section>

      <div className="audit-record-layout knowledge-layout">
        <section className="console-section audit-record-nav knowledge-list-panel">
          <ConsoleSectionHeader
            eyebrow="文档"
            title="文档分页"
            meta={<span className="console-plain-meta">第 {initialList.pagination.page} / {initialList.pagination.total_pages} 页</span>}
          />

          {initialList.documents.length === 0 ? (
            <ConsoleEmptyState title="知识库为空" detail="先录入至少一份文档，聊天检索工具才会有可用上下文。" />
          ) : (
            <div className="audit-record-list">
              {initialList.documents.map((item) => (
                <button
                  key={item.document_id}
                  type="button"
                  className={cn('audit-record-item', item.document_id === activeDocumentId && 'is-active')}
                  onClick={() => navigate({ document: item.document_id, chunkPage: '1' })}
                >
                  <div className="audit-record-item-head">
                    <strong>{item.title}</strong>
                    <time>{formatDateTime(item.updated_at)}</time>
                  </div>
                  <p>{item.source_uri || '未提供来源地址'}</p>
                  <div className="audit-record-badges">
                    <Badge tone={item.status === 'ready' ? 'success' : 'warning'}>{item.status}</Badge>
                    <Badge>{item.chunk_count} chunks</Badge>
                  </div>
                  <div className="audit-record-meta">
                    <span>{item.created_by || 'system'}</span>
                    <span>{item.document_id}</span>
                  </div>
                </button>
              ))}
            </div>
          )}

          <div className="knowledge-pagination">
            <Button
              variant="secondary"
              disabled={!initialList.pagination.has_prev}
              onClick={() => navigate({ page: String(initialList.pagination.page - 1), document: null, chunkPage: null })}
            >
              上一页
            </Button>
            <span>
              {initialList.pagination.page} / {initialList.pagination.total_pages}
            </span>
            <Button
              variant="secondary"
              disabled={!initialList.pagination.has_next}
              onClick={() => navigate({ page: String(initialList.pagination.page + 1), document: null, chunkPage: null })}
            >
              下一页
            </Button>
          </div>
        </section>

        <section className="console-section audit-record-detail knowledge-detail-panel">
          <ConsoleSectionHeader
            eyebrow="切片"
            title="文档详情"
            meta={<span className="console-plain-meta">检索上下文预览</span>}
          />

          {!initialDetail ? (
            <ConsoleEmptyState title="未选择文档" detail="从左侧选择一份知识文档后，这里会显示切片详情与检索上下文。" />
          ) : (
            <div className="audit-detail-panel">
              <header className="audit-detail-head">
                <div className="audit-detail-title">
                  <h3>{initialDetail.document.title}</h3>
                  <p>{initialDetail.document.source_uri || '未提供来源地址'}</p>
                </div>
                <div className="audit-record-badges">
                  <Badge tone={initialDetail.document.status === 'ready' ? 'success' : 'warning'}>
                    {initialDetail.document.status}
                  </Badge>
                  <Badge>{initialDetail.document.chunk_count} chunks</Badge>
                </div>
              </header>

              <div className="audit-detail-meta-grid">
                <div className="audit-detail-meta-item">
                  <span>文档 ID</span>
                  <strong>{initialDetail.document.document_id}</strong>
                </div>
                <div className="audit-detail-meta-item">
                  <span>更新时间</span>
                  <strong>{formatDateTime(initialDetail.document.updated_at)}</strong>
                </div>
                <div className="audit-detail-meta-item">
                  <span>摘要</span>
                  <strong>{initialDetail.document.preview || '--'}</strong>
                </div>
              </div>

              <div className="knowledge-chunk-list">
                {initialDetail.chunks.map((chunk) => (
                  <article key={chunk.chunk_id} className="knowledge-chunk-card">
                    <div className="knowledge-chunk-head">
                      <strong>Chunk #{chunk.chunk_index + 1}</strong>
                      <Badge>{chunk.chunk_id}</Badge>
                    </div>
                    <p>{chunk.content}</p>
                  </article>
                ))}
              </div>

              <div className="knowledge-detail-footer">
                <div className="knowledge-pagination">
                  <Button
                    variant="secondary"
                    disabled={!initialDetail.pagination.has_prev}
                    onClick={() => navigate({ document: activeDocumentId, chunkPage: String(initialDetail.pagination.page - 1) })}
                  >
                    上一批
                  </Button>
                  <span>
                    {initialDetail.pagination.page} / {initialDetail.pagination.total_pages}
                  </span>
                  <Button
                    variant="secondary"
                    disabled={!initialDetail.pagination.has_next}
                    onClick={() => navigate({ document: activeDocumentId, chunkPage: String(initialDetail.pagination.page + 1) })}
                  >
                    下一批
                  </Button>
                </div>
                <Button variant="secondary" disabled={isPending} onClick={() => removeDocument(activeDocumentId)}>
                  删除当前文档
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
