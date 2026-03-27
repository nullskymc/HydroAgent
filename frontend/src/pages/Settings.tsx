import { useState, useEffect } from 'react';
import { Save, Sliders, Bell, Server, Database, Code } from 'lucide-react';
import { api } from '../api';

export default function Settings() {
  const [config, setConfig] = useState({
    auto_irrigation: true,
    soil_moisture_threshold: 40,
    irrigation_duration_minutes: 30,
    temperature_alert_threshold: 35
  });

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getSettings().then((res: any) => setConfig(res)).catch(console.error);
  }, []);

  const handleChange = (key: string, value: any) => {
    setConfig(c => ({ ...c, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateSettings(config);
      alert('系统设置已成功更新。');
    } catch(e) { console.error(e); }
    finally { setSaving(false); }
  };

  return (
    <div className="page-settings">
      <div className="page-header" style={{ marginBottom: '2.5rem' }}>
        <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <SettingsIcon /> 参数配置中心
        </h1>
        <button className="v-btn v-btn-primary" onClick={handleSave} disabled={saving}>
          <Save size={16} /> {saving ? '保存中...' : '应用变更'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '2rem' }}>
        
        {/* Policy Section */}
        <div className="v-card">
          <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border-color)' }}>
            <Sliders size={18} /> 自动化策略配置
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.8rem' }}>
                <label style={{ fontWeight: 500 }}>AI 自动化接管</label>
                <label className="toggle-switch">
                  <input type="checkbox" checked={config.auto_irrigation} onChange={e => handleChange('auto_irrigation', e.target.checked)} />
                  <span className="slider"></span>
                </label>
              </div>
              <p style={{ color: 'var(--text-dim)', fontSize: '0.85rem' }}>允许 HydroAgent 在检测到干旱时自主启动灌溉设备。</p>
            </div>
            
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <label style={{ fontWeight: 500 }}>智能触发界限 (湿度%)</label>
                <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>{config.soil_moisture_threshold}%</span>
              </div>
              <input type="range" className="v-input" min="10" max="70" step="1" 
                value={config.soil_moisture_threshold} 
                onChange={e => handleChange('soil_moisture_threshold', parseInt(e.target.value))} 
              />
              <p style={{ color: 'var(--text-dim)', fontSize: '0.85rem', marginTop: '0.5rem' }}>当预测值或当前监测值低于此边界时触发决策流。</p>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <label style={{ fontWeight: 500 }}>单次灌溉上限时长</label>
                <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>{config.irrigation_duration_minutes} 分钟</span>
              </div>
              <input type="range" className="v-input" min="5" max="120" step="5" 
                value={config.irrigation_duration_minutes} 
                onChange={e => handleChange('irrigation_duration_minutes', parseInt(e.target.value))} 
              />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Status Section */}
          <div className="v-card">
            <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border-color)' }}>
              <Bell size={18} /> 监控报警
            </h3>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <label style={{ fontWeight: 500 }}>高温预警界限</label>
                <span style={{ color: 'var(--accent-red)', fontWeight: 600 }}>{config.temperature_alert_threshold}°C</span>
              </div>
              <input type="range" className="v-input" min="20" max="50" step="1" 
                value={config.temperature_alert_threshold} 
                onChange={e => handleChange('temperature_alert_threshold', parseInt(e.target.value))} 
              />
            </div>
          </div>

          <div className="v-card" style={{ flex: 1 }}>
             <h3 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border-color)' }}>
              <Server size={18} /> 架构参数
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.9rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Code size={14} /> 前端栈</span>
                <span style={{ fontWeight: 500 }}>React 18 / Vite / Lucide</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Database size={14} /> 协议层</span>
                <span style={{ fontWeight: 500 }}>Model Context Protocol (v1)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Server size={14} /> 核心版本</span>
                <span style={{ fontWeight: 500, fontFamily: 'var(--font-mono)' }}>v4.0.0-react</span>
              </div>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}

function SettingsIcon() {
  return <Sliders size={24} />
}
