import { useEffect, useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { Activity, Bot, History, Settings, Waves } from 'lucide-react';
import { api } from '../../api';

export function Layout() {
  const [status, setStatus] = useState<'online' | 'offline' | 'connecting'>('connecting');
  const [version, setVersion] = useState<string>('');
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    // Clock
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    // Status check
    api.getStatus()
      .then((res: any) => {
        if (res.status === 'online') {
          setStatus('online');
          setVersion(res.version || '');
        } else {
          setStatus('offline');
        }
      })
      .catch(() => setStatus('offline'));
  }, []);

  return (
    <div className="app-container">
      <nav className="navbar">
        <div className="nav-brand">
          <Waves size={20} color="var(--accent-blue)" />
          <span>HydroAgent <span style={{ color: 'var(--text-dim)', fontWeight: 400, marginLeft: 4 }}>水利智能体</span></span>
        </div>
        <div className="nav-links">
          <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Activity size={16} />
            实时监控
          </NavLink>
          <NavLink to="/agent" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Bot size={16} />
            智能助手
          </NavLink>
          <NavLink to="/history" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <History size={16} />
            决策日志
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Settings size={16} />
            设置
          </NavLink>
        </div>
        <div className="nav-status">
          <div className={`status-dot ${status !== 'online' ? 'offline' : ''}`} />
          <span>
            {status === 'connecting' ? '连接中...' : 
             status === 'online' ? `引擎就绪 ${version ? `(v${version})` : ''}` : '系统离线'}
          </span>
          <span style={{ marginLeft: 8, fontVariantNumeric: 'tabular-nums' }}>
            {time.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </nav>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
