import { AppShell } from '@/components/app-shell'
import { ChatPanelShell } from '@/components/chat-panel-shell'
import { getSessionToken, requirePermission } from '@/lib/auth'
import { fetchBackendJson } from '@/lib/backend'
import { ConversationDetail, ConversationSummary } from '@/lib/types'

export default async function ChatPage({
  searchParams,
}: {
  searchParams?: Promise<{ prompt?: string; autosend?: string; fresh?: string }>
}) {
  await requirePermission('chat:view')
  const resolvedSearchParams = (await searchParams) || {}
  const initialPrompt = typeof resolvedSearchParams.prompt === 'string' ? resolvedSearchParams.prompt : ''
  const autoSendInitialPrompt = resolvedSearchParams.autosend === '1' && initialPrompt.trim().length > 0
  const startFresh = resolvedSearchParams.fresh === '1'
  const authToken = await getSessionToken()
  const conversationsPayload = await fetchBackendJson<{ conversations: ConversationSummary[] }>('/api/conversations', { authToken }).catch(() => ({
    conversations: [],
  }))
  const firstConversation = conversationsPayload.conversations[0]
  const initialActiveConversation = firstConversation
    ? await fetchBackendJson<ConversationDetail>(`/api/conversations/${firstConversation.session_id}`, { authToken }).catch(() => null)
    : null

  return (
    <AppShell currentPath="/chat">
      <div className="chat-page-frame">
        <ChatPanelShell
          initialConversations={conversationsPayload.conversations}
          initialActiveConversation={initialActiveConversation}
          initialPrompt={initialPrompt}
          autoSendInitialPrompt={autoSendInitialPrompt}
          startFreshConversation={startFresh}
        />
      </div>
    </AppShell>
  )
}
