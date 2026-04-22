import { createElement, Fragment, type ElementType, type ReactNode } from 'react'
import { marked, type Token, type Tokens } from 'marked'

const markdownOptions = {
  gfm: true,
  breaks: true,
} as const

function renderInlineTokens(tokens: Token[] | undefined, keyPrefix: string): ReactNode[] {
  if (!tokens || tokens.length === 0) return []

  return tokens.map((token, index) => {
    const key = `${keyPrefix}-${index}`

    switch (token.type) {
      case 'strong':
        return <strong key={key}>{renderInlineTokens(token.tokens, key)}</strong>
      case 'em':
        return <em key={key}>{renderInlineTokens(token.tokens, key)}</em>
      case 'del':
        return <del key={key}>{renderInlineTokens(token.tokens, key)}</del>
      case 'codespan':
        return (
          <code key={key} className="message-inline-code">
            {token.text}
          </code>
        )
      case 'br':
        return <br key={key} />
      case 'link':
        return (
          <a key={key} href={token.href} target="_blank" rel="noreferrer">
            {renderInlineTokens(token.tokens, key)}
          </a>
        )
      case 'image':
        return <img key={key} src={token.href} alt={token.text} title={token.title || undefined} />
      case 'html':
        // 聊天消息里的原始 HTML 一律按纯文本展示，避免引入脚本或意外布局。
        return <Fragment key={key}>{token.text}</Fragment>
      case 'text':
        return token.tokens ? <Fragment key={key}>{renderInlineTokens(token.tokens, key)}</Fragment> : <Fragment key={key}>{token.text}</Fragment>
      case 'escape':
        return <Fragment key={key}>{token.text}</Fragment>
      default:
        return 'text' in token ? <Fragment key={key}>{token.text}</Fragment> : null
    }
  })
}

function renderListItemContent(item: Tokens.ListItem, keyPrefix: string): ReactNode {
  if (item.tokens.length === 1) {
    const [token] = item.tokens
    if (token.type === 'text') {
      return (
        <>
          {item.task ? <input type="checkbox" disabled checked={Boolean(item.checked)} readOnly /> : null}
          {renderInlineTokens(token.tokens || [token], keyPrefix)}
        </>
      )
    }
    if (token.type === 'paragraph') {
      return (
        <>
          {item.task ? <input type="checkbox" disabled checked={Boolean(item.checked)} readOnly /> : null}
          {renderInlineTokens(token.tokens, keyPrefix)}
        </>
      )
    }
  }

  return (
    <>
      {item.task ? <input type="checkbox" disabled checked={Boolean(item.checked)} readOnly /> : null}
      {renderBlockTokens(item.tokens, keyPrefix)}
    </>
  )
}

function renderTableCell(cell: Tokens.TableCell, key: string, cellTag: 'th' | 'td') {
  return createElement(
    cellTag,
    {
      key,
      style: cell.align ? { textAlign: cell.align } : undefined,
    },
    renderInlineTokens(cell.tokens, key),
  )
}

function renderBlockTokens(tokens: Token[] | undefined, keyPrefix: string): ReactNode[] {
  if (!tokens || tokens.length === 0) return []

  return tokens.flatMap((token, index) => {
    const key = `${keyPrefix}-${index}`

    switch (token.type) {
      case 'space':
      case 'def':
        return []
      case 'heading': {
        const depth = Math.min(Math.max(token.depth, 1), 6)
        const headingTags: Record<number, ElementType> = {
          1: 'h1',
          2: 'h2',
          3: 'h3',
          4: 'h4',
          5: 'h5',
          6: 'h6',
        }
        const headingTag = headingTags[depth]
        return createElement(headingTag, { key }, renderInlineTokens(token.tokens, key))
      }
      case 'paragraph':
        return <p key={key}>{renderInlineTokens(token.tokens, key)}</p>
      case 'text':
        return token.tokens ? <p key={key}>{renderInlineTokens(token.tokens, key)}</p> : <p key={key}>{token.text}</p>
      case 'list': {
        const listTag = token.ordered ? 'ol' : 'ul'
        return createElement(
          listTag,
          {
            key,
            start: token.ordered && typeof token.start === 'number' ? token.start : undefined,
          },
          token.items.map((item: Tokens.ListItem, itemIndex: number) => (
            <li key={`${key}-item-${itemIndex}`}>{renderListItemContent(item, `${key}-item-${itemIndex}`)}</li>
          )),
        )
      }
      case 'blockquote':
        return <blockquote key={key}>{renderBlockTokens(token.tokens, key)}</blockquote>
      case 'code':
        return (
          <pre key={key}>
            <code className={token.lang ? `language-${token.lang}` : undefined}>{token.text}</code>
          </pre>
        )
      case 'hr':
        return <hr key={key} />
      case 'table':
        return (
          <div key={key} className="markdown-table-wrap">
            <table className="markdown-table">
              <thead>
                <tr>
                  {token.header.map((cell: Tokens.TableCell, cellIndex: number) => renderTableCell(cell, `${key}-head-${cellIndex}`, 'th'))}
                </tr>
              </thead>
              <tbody>
                {token.rows.map((row: Tokens.TableCell[], rowIndex: number) => (
                  <tr key={`${key}-row-${rowIndex}`}>
                    {row.map((cell: Tokens.TableCell, cellIndex: number) => renderTableCell(cell, `${key}-row-${rowIndex}-${cellIndex}`, 'td'))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      case 'html':
        return <p key={key}>{token.text}</p>
      default:
        return 'tokens' in token && Array.isArray(token.tokens)
          ? <Fragment key={key}>{renderInlineTokens(token.tokens, key)}</Fragment>
          : 'text' in token
            ? <p key={key}>{token.text}</p>
            : []
    }
  })
}

export function MessageRichText({ content }: { content: string }) {
  const tokens = marked.lexer(content, markdownOptions)

  return <div className="markdown-content message-rich-text">{renderBlockTokens(tokens, 'md')}</div>
}
