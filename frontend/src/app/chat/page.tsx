import { ChatShell } from '@/components/app-shell'
import { ChatPanel } from '@/components/chat-panel'
import { getSessionToken, requirePermission } from '@/lib/auth'
import { fetchBackendJson } from '@/lib/backend'
import { ConversationDetail, ConversationSummary } from '@/lib/types'

export default async function ChatPage() {
  await requirePermission('chat:view')
  const authToken = await getSessionToken()
  const conversationsPayload = await fetchBackendJson<{ conversations: ConversationSummary[] }>('/api/conversations', { authToken }).catch(() => ({
    conversations: [],
  }))
  const firstConversation = conversationsPayload.conversations[0]
  const initialActiveConversation = firstConversation
    ? await fetchBackendJson<ConversationDetail>(`/api/conversations/${firstConversation.session_id}`, { authToken }).catch(() => null)
    : null

  return (
    <ChatShell currentPath="/chat">
      <ChatPanel
        initialConversations={conversationsPayload.conversations}
        initialActiveConversation={initialActiveConversation}
      />
    </ChatShell>
  )
}
