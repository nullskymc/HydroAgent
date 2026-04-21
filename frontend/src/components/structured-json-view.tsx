import { StructuredJsonNode, StructuredJsonSection } from '@/lib/types'

function StructuredJsonValue({ node, depth = 0 }: { node: StructuredJsonNode; depth?: number }) {
  if (node.kind === 'primitive') {
    return <span className="structured-json-value">{String(node.value ?? '--')}</span>
  }

  if (node.kind === 'empty') {
    return <span className="structured-json-empty">无数据</span>
  }

  const children = node.children || []
  // 复杂载荷默认收起，避免长 JSON 抢占审计详情区高度。
  const defaultOpen = depth === 0 && children.length > 0 && children.length <= 3

  return (
    <details className="structured-json-branch" open={defaultOpen}>
      <summary>
        <span>{node.label}</span>
        <span>{node.summary}</span>
      </summary>
      <div className="structured-json-children">
        {children.map((child) => (
          <StructuredJsonNodeView key={`${node.key}-${child.key}`} node={child} depth={depth + 1} />
        ))}
      </div>
    </details>
  )
}

function StructuredJsonNodeView({ node, depth = 0 }: { node: StructuredJsonNode; depth?: number }) {
  if (node.kind === 'primitive' || node.kind === 'empty') {
    return (
      <div className="structured-json-row">
        <span className="structured-json-label">{node.label}</span>
        <div className="structured-json-cell">
          <StructuredJsonValue node={node} depth={depth} />
        </div>
      </div>
    )
  }

  return (
    <div className="structured-json-row structured-json-row-block">
      <StructuredJsonValue node={node} depth={depth} />
    </div>
  )
}

export function StructuredJsonSectionView({ section }: { section: StructuredJsonSection }) {
  return (
    <section className="structured-json-section">
      <header className="structured-json-section-head">
        <div>
          <strong>{section.title}</strong>
          {section.description ? <p>{section.description}</p> : null}
        </div>
      </header>
      <div className="structured-json-panel">
        {section.nodes.length === 0 ? (
          <div className="structured-json-empty-state">无数据</div>
        ) : (
          section.nodes.map((node) => <StructuredJsonNodeView key={`${section.title}-${node.key}`} node={node} />)
        )}
      </div>
    </section>
  )
}
