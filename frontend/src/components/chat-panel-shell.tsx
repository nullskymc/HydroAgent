'use client'

import { useEffect, useState } from 'react'
import { ChatPanel } from '@/components/chat-panel'
import { ConversationDetail, ConversationSummary } from '@/lib/types'

type ChatPanelShellProps = {
  initialConversations: ConversationSummary[]
  initialActiveConversation: ConversationDetail | null
  initialPrompt?: string
  autoSendInitialPrompt?: boolean
  startFreshConversation?: boolean
}

function ChatLoadingShell() {
  return (
    <div className="chat-loading-shell">
      <p className="eyebrow">HydroAgent</p>
      <h2>正在加载智能对话</h2>
      <p>正在准备会话、计划与工具轨迹。</p>
    </div>
  )
}

export function ChatPanelShell(props: ChatPanelShellProps) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return <ChatLoadingShell />
  }

  return <ChatPanel {...props} />
}
