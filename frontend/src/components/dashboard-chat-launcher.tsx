import Link from 'next/link'
import { Bot, SendHorizontal } from 'lucide-react'

export function DashboardChatLauncher({ compact = false }: { compact?: boolean }) {
  if (!compact) {
    return (
      <section className="rounded-lg bg-white p-3 shadow-sm">
        <div className="mb-3 flex items-center justify-between gap-3 px-1">
          <div>
            <p className="eyebrow">智能体</p>
            <h2 className="m-0 mt-1 text-base font-semibold leading-none text-slate-950">快速发起对话</h2>
          </div>
          <div className="flex size-9 items-center justify-center rounded-lg bg-blue-50 text-[#0052FF]">
            <Bot className="size-4" aria-hidden="true" />
          </div>
        </div>

        <form action="/chat" method="GET" className="flex flex-col gap-2">
          <input type="hidden" name="autosend" value="1" />
          <input type="hidden" name="fresh" value="1" />
          <div className="flex h-14 items-center gap-3 rounded-lg bg-white px-3 shadow-sm ring-1 ring-slate-200 transition focus-within:ring-2 focus-within:ring-blue-500/30">
            <Bot className="size-4 shrink-0 text-[#0052FF]" aria-hidden="true" />
            <input
              name="prompt"
              className="min-w-0 flex-1 bg-transparent text-base font-medium text-slate-900 outline-none placeholder:text-sm placeholder:font-normal placeholder:text-slate-400"
              placeholder="例如：分析当前分区湿度并给出是否需要生成灌溉计划的建议"
            />
            <button type="submit" className="console-chat-submit shrink-0">
              <SendHorizontal size={14} />
              <span>发送</span>
            </button>
          </div>
          <div className="flex items-center justify-between gap-3 px-1">
            <p className="m-0 text-xs leading-5 text-slate-500">提交后会自动进入智能对话页，并以新会话发起本轮咨询。</p>
            <Link href="/chat" className="text-xs font-semibold text-[#0052FF] hover:underline">
              打开聊天页
            </Link>
          </div>
        </form>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="console-section-header">
        <div>
          <p className="eyebrow">智能体</p>
          <h2>快速发起对话</h2>
        </div>
        <Bot className="size-4" />
      </div>

      <form action="/chat" method="GET" className="console-chat-launcher">
        <input type="hidden" name="autosend" value="1" />
        <input type="hidden" name="fresh" value="1" />
        <div className="command-bar-shell">
          <input
            name="prompt"
            className="min-w-0 flex-1 bg-transparent px-2 text-sm text-slate-900 outline-none placeholder:text-slate-400"
            placeholder="例如：分析当前分区湿度并给出是否需要生成灌溉计划的建议"
          />
          <button type="submit" className="console-chat-submit">
            <SendHorizontal size={14} />
            <span>发送</span>
          </button>
        </div>
        <div className="console-chat-actions">
          <Link href="/chat" className="console-chat-link">
            只打开聊天页
          </Link>
        </div>
        {!compact ? <p className="console-chat-hint">提交后会自动进入智能对话页，并以新会话发起本轮咨询。</p> : null}
      </form>
    </section>
  )
}
