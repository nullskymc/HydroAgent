import { useEffect, useState } from 'react';
import { History as HistoryIcon, LogOut, CheckCircle, Search } from 'lucide-react';
import { api } from '../api';

export default function History() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [filter, setFilter] = useState('all');

  const loadData = async () => {
    try {
      const res = await api.getDecisions(50);
      setDecisions(res.decisions || []);
    } catch(e) { console.error(e); }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="page-history">
      <div className="page-header">
        <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <HistoryIcon size={24} /> 系统审计日志
        </h1>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <select className="v-select" style={{ width: 140 }} value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">所有记录</option>
            <option value="decision">AI 决策</option>
            <option value="manual">手动干预</option>
          </select>
          <button className="v-btn" onClick={loadData}>
            <Search size={16} /> 查询
          </button>
        </div>
      </div>

      <div className="v-card" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
          <thead style={{ backgroundColor: 'var(--card-bg)', borderBottom: '1px solid var(--border-color)' }}>
            <tr>
              <th style={{ padding: '1rem 1.5rem', fontWeight: 500, color: 'var(--text-dim)' }}>时间</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: 500, color: 'var(--text-dim)' }}>事件类型</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: 500, color: 'var(--text-dim)' }}>详情摘要</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: 500, color: 'var(--text-dim)' }}>操作人</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: 500, color: 'var(--text-dim)' }}>状态</th>
            </tr>
          </thead>
          <tbody>
            {decisions.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-dim)' }}>暂无记录</td></tr>
            ) : decisions.map((d, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border-color)' }}>
                <td style={{ padding: '1rem 1.5rem' }}>{new Date(d.timestamp).toLocaleString('zh-CN')}</td>
                <td style={{ padding: '1rem 1.5rem' }}>
                  <span style={{ padding: '0.2rem 0.6rem', borderRadius: '4px', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)', fontSize: '0.8rem' }}>
                    {d.action || '数据分析'}
                  </span>
                </td>
                <td style={{ padding: '1rem 1.5rem', color: 'var(--text-dim)' }}>{d.reason || d.summary || '-'}</td>
                <td style={{ padding: '1rem 1.5rem' }}>{d.source || 'HydroAgent Core'}</td>
                <td style={{ padding: '1rem 1.5rem' }}>
                   {d.status === 'success' || !d.status ? <CheckCircle size={16} color="var(--accent-green)" /> : <LogOut size={16} color="var(--accent-red)" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
