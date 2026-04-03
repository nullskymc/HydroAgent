import Link from 'next/link'
import { Bot, SendHorizontal } from 'lucide-react'

export function DashboardChatLauncher() {
  return (
    <section className="console-section">
      <div className="console-section-header">
        <div>
          <p className="eyebrow">智能体</p>
          <h2>快速发起对话</h2>
        </div>
        <Bot size={16} />
      </div>

      <form action="/chat" method="GET" className="console-chat-launcher">
        <input type="hidden" name="autosend" value="1" />
        <input type="hidden" name="fresh" value="1" />
        <textarea
          name="prompt"
          className="console-chat-textarea"
          rows={4}
          placeholder="例如：分析当前分区湿度并给出是否需要生成灌溉计划的建议"
        />
        <div className="console-chat-actions">
          <button type="submit" className="console-chat-submit">
            <SendHorizontal size={14} />
            <span>发送并进入对话</span>
          </button>
          <Link href="/chat" className="console-chat-link">
            只打开聊天页
          </Link>
        </div>
        <p className="console-chat-hint">提交后会自动进入智能对话页，并以新会话发起本轮咨询。</p>
      </form>
    </section>
  )
}
