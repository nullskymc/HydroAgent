import { Fragment, ReactNode } from 'react'

function renderInline(text: string): ReactNode[] {
  const tokens = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean)
  return tokens.map((token, index) => {
    if (token.startsWith('`') && token.endsWith('`')) {
      return (
        <code key={`${token}-${index}`} className="message-inline-code">
          {token.slice(1, -1)}
        </code>
      )
    }
    if (token.startsWith('**') && token.endsWith('**')) {
      return <strong key={`${token}-${index}`}>{token.slice(2, -2)}</strong>
    }
    return <Fragment key={`${token}-${index}`}>{token}</Fragment>
  })
}

type Block =
  | { type: 'paragraph'; content: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'heading'; level: number; content: string }

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let index = 0

  while (index < lines.length) {
    const rawLine = lines[index]
    const line = rawLine.trim()

    if (!line) {
      index += 1
      continue
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/)
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length,
        content: headingMatch[2].trim(),
      })
      index += 1
      continue
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'list', ordered: false, items })
      continue
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'list', ordered: true, items })
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const current = lines[index].trim()
      if (!current || /^(#{1,3})\s+/.test(current) || /^[-*]\s+/.test(current) || /^\d+\.\s+/.test(current)) {
        break
      }
      paragraphLines.push(current)
      index += 1
    }
    blocks.push({ type: 'paragraph', content: paragraphLines.join(' ') })
  }

  return blocks
}

export function MessageRichText({ content }: { content: string }) {
  const blocks = parseBlocks(content)

  return (
    <div className="markdown-content message-rich-text">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const HeadingTag = block.level === 1 ? 'h3' : block.level === 2 ? 'h4' : 'h5'
          return <HeadingTag key={`heading-${index}`}>{renderInline(block.content)}</HeadingTag>
        }

        if (block.type === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul'
          return (
            <ListTag key={`list-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`item-${itemIndex}`}>{renderInline(item)}</li>
              ))}
            </ListTag>
          )
        }

        return <p key={`paragraph-${index}`}>{renderInline(block.content)}</p>
      })}
    </div>
  )
}
