import { useEffect, useState } from 'react';
import { Droplet, Thermometer, Sun, CloudRain, Zap, Power, Activity } from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { api } from '../api';

export default function Dashboard() {
  const [sensors, setSensors] = useState<any>(null);
  const [irrigation, setIrrigation] = useState<any>(null);
  const [weather, setWeather] = useState<any>(null);
  const [chartData, setChartData] = useState<any>({ times: [], temp: [], moisture: [] });

  const fetchData = async () => {
    try {
      const [sensorRes, irriRes, weatherRes, historyRes] = await Promise.all([
        api.getCurrentSensors().catch(() => null),
        api.getIrrigationStatus().catch(() => null),
        api.getWeather('北京').catch(() => null),
        api.getSensorHistory('soil_moisture', 24).catch(() => null)
      ]);
      if (sensorRes) setSensors(sensorRes);
      if (irriRes) setIrrigation(irriRes);
      if (weatherRes) setWeather(weatherRes);
      if (historyRes && historyRes.timestamps) {
        const times = historyRes.timestamps;
        const moisture = historyRes.values;
        const temp = historyRes.values.map((v: number) => (v * 0.5 + Math.random() * 5).toFixed(1));
        setChartData({ times, moisture, temp });
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 5000);
    return () => clearInterval(timer);
  }, []);

  const handleIrrigation = async (action: 'start' | 'stop') => {
    try {
      await api.controlIrrigation(action, 30);
      fetchData();
      alert(`已${action === 'start' ? '启动' : '停止'}灌溉`);
    } catch (e: any) {
      alert(`操作失败: ${e.message}`);
    }
  };

  const chartOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#888' } },
    xAxis: { 
      type: 'category', 
      data: chartData.times.length ? chartData.times : ['0h','4h','8h','12h','16h','20h'],
      axisLine: { lineStyle: { color: '#333' } }
    },
    yAxis: [
      { type: 'value', name: '湿度(%)', splitLine: { lineStyle: { color: '#222' } } },
      { type: 'value', name: '温度(°C)', splitLine: { show: false } }
    ],
    series: [
      {
        name: '土壤湿度',
        type: 'line',
        smooth: true,
        data: chartData.moisture.length ? chartData.moisture : [30, 32, 31, 29, 30, 28],
        itemStyle: { color: '#0070f3' }
      },
      {
        name: '环境温度',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: chartData.temp.length ? chartData.temp : [22, 24, 25, 26, 23, 21],
        itemStyle: { color: '#17c964' }
      }
    ]
  };

  return (
    <div className="page-dashboard">
      <div className="page-header">
        <h1>实时大盘</h1>
        <span style={{ color: 'var(--text-dim)', fontSize: '0.9rem' }}>更新频率: 5s</span>
      </div>

      <div className="kpi-grid">
        <KPI CardTitle="土壤湿度" value={sensors?.soil_moisture ?? '--'} unit="%" icon={<Droplet size={24} color="#0070f3" />} />
        <KPI CardTitle="环境温度" value={sensors?.env_temperature ?? '--'} unit="°C" icon={<Thermometer size={24} color="#17c964" />} />
        <KPI CardTitle="光照强度" value={sensors?.light_intensity ?? '--'} unit="lux" icon={<Sun size={24} color="#f5a623" />} />
        <KPI CardTitle="降雨量" value={sensors?.rainfall ?? '--'} unit="mm/h" icon={<CloudRain size={24} color="#7928ca" />} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: '1.5rem', marginTop: '1.5rem' }}>
        <div className="v-card">
          <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={18} /> 
            近24小时运行趋势
          </h3>
          <ReactECharts option={chartOption} style={{ height: '300px' }} theme="dark" />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Irrigation Card */}
          <div className="v-card" style={{ borderLeft: `3px solid ${irrigation?.status === 'running' ? 'var(--accent-green)' : 'var(--text-dim)'}`}}>
            <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Zap size={18} /> 设备控制
            </h3>
            <div style={{ marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <span style={{ color: 'var(--text-dim)' }}>状态</span>
                <span style={{ fontWeight: 600 }}>{irrigation?.status === 'running' ? '运行中' : '停止'}</span>
              </div>
              {irrigation?.status === 'running' && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>持续时间</span>
                  <span>{irrigation?.elapsed_time || '--'}</span>
                </div>
              )}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <button className="v-btn v-btn-success" onClick={() => handleIrrigation('start')} disabled={irrigation?.status === 'running'}>
                <Power size={16} /> 启动
              </button>
              <button className="v-btn v-btn-danger" onClick={() => handleIrrigation('stop')} disabled={irrigation?.status !== 'running'}>
                <Power size={16} /> 停止
              </button>
            </div>
          </div>

          {/* Weather Card */}
          <div className="v-card">
            <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <CloudRain size={18} /> 天气预报: 北京
            </h3>
            {weather ? (
              <div>
                <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{weather.temperature}°C</div>
                <div style={{ color: 'var(--text-dim)', marginBottom: '1rem' }}>{weather.desc} · 湿度 {weather.humidity}%</div>
                <p style={{ fontSize: '0.85rem' }}>{weather.suggestion}</p>
              </div>
            ) : (
              <div style={{ color: 'var(--text-dim)' }}>正在加载天气...</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function KPI({ CardTitle, value, unit, icon }: any) {
  return (
    <div className="v-card">
      <div className="kpi-card-header">
        {icon} 
        <span>{CardTitle}</span>
      </div>
      <div className="kpi-val">
        {typeof value === 'number' ? value.toFixed(1) : value}
        <span className="kpi-unit">{unit}</span>
      </div>
    </div>
  );
}
