'use client'

import { ChatPanel } from '@/components/chat-panel'
import { ConversationDetail, ConversationSummary } from '@/lib/types'

type ChatPanelShellProps = {
  initialConversations: ConversationSummary[]
  initialActiveConversation: ConversationDetail | null
  initialPrompt?: string
  autoSendInitialPrompt?: boolean
  startFreshConversation?: boolean
}

export function ChatPanelShell(props: ChatPanelShellProps) {
  return <ChatPanel {...props} />
}
