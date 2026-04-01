import { ChatShell } from '@/components/app-shell'
import { ChatPanel } from '@/components/chat-panel'
import { fetchBackendJson } from '@/lib/backend'
import { ConversationDetail, ConversationSummary } from '@/lib/types'

export default async function ChatPage() {
  const conversationsPayload = await fetchBackendJson<{ conversations: ConversationSummary[] }>('/api/conversations').catch(() => ({
    conversations: [],
  }))
  const firstConversation = conversationsPayload.conversations[0]
  const initialActiveConversation = firstConversation
    ? await fetchBackendJson<ConversationDetail>(`/api/conversations/${firstConversation.session_id}`).catch(() => null)
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
