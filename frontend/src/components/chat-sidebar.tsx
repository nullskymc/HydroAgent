import { MessageSquarePlus, Trash2 } from 'lucide-react'
import { ConversationSummary } from '@/lib/types'
import { formatDateTime } from '@/lib/utils'
import { Button } from '@/components/ui/button'

type ChatSidebarProps = {
  quickPrompts: string[]
  conversations: ConversationSummary[]
  activeConversationId?: string | null
  deletingConversationId?: string | null
  onCreateConversation: () => void
  onSelectPrompt: (prompt: string) => void
  onSelectConversation: (sessionId: string) => void
  onDeleteConversation: (sessionId: string) => void
}

function formatConversationTimestamp(value?: string | null) {
  const text = formatDateTime(value)
  return text === '--' ? '刚刚' : text.replace('/', '-')
}

function SidebarSectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="thread-sidebar-section-head">
      <span className="thread-sidebar-section-title">{title}</span>
      <strong className="thread-sidebar-section-count">{count}</strong>
    </div>
  )
}

function QuickActionList({
  prompts,
  onSelectPrompt,
}: {
  prompts: string[]
  onSelectPrompt: (prompt: string) => void
}) {
  return (
    <div className="thread-sidebar-block">
      <SidebarSectionHeader title="快捷动作" count={prompts.length} />
      <div className="thread-sidebar-prompt-list">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="thread-sidebar-prompt"
            onClick={() => {
              // 仅回填输入框，不直接发送，保留用户确认权。
              onSelectPrompt(prompt)
            }}
          >
            <span>{prompt}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function ConversationList({
  conversations,
  activeConversationId,
  deletingConversationId,
  onSelectConversation,
  onDeleteConversation,
}: {
  conversations: ConversationSummary[]
  activeConversationId?: string | null
  deletingConversationId?: string | null
  onSelectConversation: (sessionId: string) => void
  onDeleteConversation: (sessionId: string) => void
}) {
  return (
    <div className="thread-sidebar-block thread-sidebar-history">
      <SidebarSectionHeader title="最近会话" count={conversations.length} />
      {conversations.length === 0 ? (
        <div className="thread-sidebar-empty">
          <p>暂无历史会话</p>
          <p>新建会话后即可开始生成计划。</p>
        </div>
      ) : null}
      <div className="thread-sidebar-conversation-list">
        {conversations.map((conversation) => {
          const isActive = activeConversationId === conversation.session_id
          const isDeleting = deletingConversationId === conversation.session_id

          return (
            <div
              key={conversation.session_id}
              className={isActive ? 'thread-sidebar-conversation-row is-active' : 'thread-sidebar-conversation-row'}
            >
              <button
                type="button"
                className={isActive ? 'thread-sidebar-conversation is-active' : 'thread-sidebar-conversation'}
                onClick={() => {
                  // 会话切换保持单一职责，只负责请求主面板加载目标会话。
                  onSelectConversation(conversation.session_id)
                }}
              >
                <strong className="thread-sidebar-conversation-title">{conversation.title}</strong>
                <p className="thread-sidebar-conversation-time">
                  {formatConversationTimestamp(conversation.updated_at)}
                </p>
              </button>
              <Button
                size="icon"
                variant="ghost"
                className="thread-sidebar-conversation-delete"
                aria-label={`删除会话 ${conversation.title}`}
                disabled={isDeleting}
                onClick={() => {
                  // 删除按钮独立拦截，避免和会话切换动作互相串联。
                  onDeleteConversation(conversation.session_id)
                }}
              >
                <Trash2 size={14} />
              </Button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function ChatSidebar({
  quickPrompts,
  conversations,
  activeConversationId,
  deletingConversationId,
  onCreateConversation,
  onSelectPrompt,
  onSelectConversation,
  onDeleteConversation,
}: ChatSidebarProps) {
  return (
    <aside className="thread-sidebar">
      <div className="thread-sidebar-surface">
        <div className="thread-sidebar-header">
          <div className="thread-sidebar-copy">
            <p className="eyebrow">HydroAgent</p>
            <div className="thread-sidebar-header-row">
              <h2>智能对话</h2>
              <Button
                size="icon"
                variant="ghost"
                className="thread-sidebar-create-button"
                aria-label="新建对话"
                onClick={() => {
                  // 新建入口独立保留，避免和历史切换或快捷动作混合。
                  onCreateConversation()
                }}
              >
                <MessageSquarePlus size={16} />
              </Button>
            </div>
            <p>围绕分区、计划、审批和执行的统一线程。</p>
          </div>
        </div>

        <QuickActionList prompts={quickPrompts} onSelectPrompt={onSelectPrompt} />
        <ConversationList
          conversations={conversations}
          activeConversationId={activeConversationId}
          deletingConversationId={deletingConversationId}
          onSelectConversation={onSelectConversation}
          onDeleteConversation={onDeleteConversation}
        />
      </div>
    </aside>
  )
}
