import { api } from '../api';

declare global {
  interface Window {
    _refreshHistory: () => void;
  }
}

export async function render(): Promise<void> {
  const app = document.getElementById('app');
  const tpl = document.getElementById('tpl-history') as HTMLTemplateElement;
  if (!app || !tpl) return;
  
  app.innerHTML = '';
  app.appendChild(tpl.content.cloneNode(true));

  const filterEl = document.getElementById('history-filter') as HTMLSelectElement;
  if (filterEl) {
    filterEl.addEventListener('change', () => loadLogs(filterEl.value));
  }

  window._refreshHistory = () => {
    if (filterEl) loadLogs(filterEl.value);
  };

  await loadLogs(filterEl ? filterEl.value : 'decisions');
}

async function loadLogs(type: string): Promise<void> {
  const listEl = document.getElementById('decision-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="loading-state">加载中...</div>';

  try {
    if (type === 'decisions') {
      const res: any = await api.getDecisions(20);
      renderDecisions(res.decisions || []);
    } else {
      const res: any = await api.getIrrigationLogs();
      renderIrrigation(res.logs || []);
    }
  } catch (e: any) {
    listEl.innerHTML = `<div class="loading-state">❌ 加载失败: ${e.message}</div>`;
  }
}

function renderDecisions(decisions: any[]): void {
  const listEl = document.getElementById('decision-list');
  if (!listEl) return;

  const total = decisions.length;
  const auto = decisions.filter((d: any) => d.trigger === 'auto').length;
  updateText('stat-total', total.toString());
  updateText('stat-auto', auto.toString());
  updateText('stat-manual', (total - auto).toString());

  if (decisions.length === 0) {
    listEl.innerHTML = '<div class="empty-state">暂无 Agent 决策记录</div>';
    return;
  }

  listEl.innerHTML = decisions.map((d: any) => {
    const time = new Date(d.created_at).toLocaleString('zh-CN', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
    const tools = d.tools_used || [];
    const triggerLabel = d.trigger === 'auto' ? '自动' : '对话';
    
    let html = `<div class="decision-item">
      <div class="decision-header">
        <span class="decision-action">${d.decision_result?.action || '综合分析'}</span>
        <span class="decision-trigger">${triggerLabel}</span>
        <span class="decision-time">${time}</span>
      </div>`;
    if (tools.length > 0) {
      html += `<div class="decision-tools">${tools.map((t: string) => `<span class="tool-badge">${t}</span>`).join('')}</div>`;
    }
    if (d.reflection_notes) {
      html += `<div class="decision-reflection"><strong>反思:</strong> ${d.reflection_notes}</div>`;
    }
    html += `</div>`;
    return html;
  }).join('');
}

function renderIrrigation(logs: any[]): void {
  const listEl = document.getElementById('decision-list');
  if (!listEl) return;
  updateText('stat-total', logs.length.toString());
  updateText('stat-auto', '--');
  updateText('stat-manual', '--');

  if (logs.length === 0) {
    listEl.innerHTML = '<div class="empty-state">暂无灌溉历史记录</div>';
    return;
  }

  listEl.innerHTML = logs.map((l: any) => {
    const time = new Date(l.created_at).toLocaleString('zh-CN', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
    const plannedStr = l.duration_planned ? `${Math.round(l.duration_planned / 60)} 分钟` : '未知';
    return `<div class="decision-item">
      <div class="decision-header">
        <span class="decision-action">${l.event === 'start' ? '▶ 启动灌溉' : '⏹ 停止灌溉'}</span>
        <span class="decision-trigger">${l.status}</span>
        <span class="decision-time">${time}</span>
      </div>
      <div class="decision-reflection">
        <strong>操作详情:</strong> ${l.message || '无备注'}<br>
        ${l.event === 'start' ? `<strong>计划时长:</strong> ${plannedStr}` : ''}
      </div>
    </div>`;
  }).join('');
}

function updateText(id: string, text: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
