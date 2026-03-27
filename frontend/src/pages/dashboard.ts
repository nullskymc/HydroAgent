/**
 * Dashboard Page — Real-time Sensor Monitoring
 */
import { api } from '../api';
import * as echarts from 'echarts';

let chart: echarts.ECharts | null = null;
let refreshTimer: number | null = null;
let prevMoisture: number | null = null;
let currentHours = 6;

const weatherIcons: Record<string, string> = {
  '晴': '☀️', '多云': '⛅', '阴': '🌥️', '小雨': '🌦️',
  '中雨': '🌧️', '大雨': '⛈️', '阵雨': '🌦️', '雪': '❄️', '雾': '🌫️',
};

function getWeatherIcon(weather: string): string {
  for (const [k, v] of Object.entries(weatherIcons)) {
    if (weather && weather.includes(k)) return v;
  }
  return '🌤️';
}

declare global {
  interface Window {
    _startIrrigation: () => void;
    _stopIrrigation: () => void;
    _askAnalysis: () => void;
    _askForecast: () => void;
  }
}

export async function render(): Promise<void> {
  const app = document.getElementById('app');
  const tpl = document.getElementById('tpl-dashboard') as HTMLTemplateElement;
  if (!app || !tpl) return;
  
  app.innerHTML = '';
  app.appendChild(tpl.content.cloneNode(true));

  // Bind chart time tabs
  document.querySelectorAll('.time-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.time-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentHours = parseInt((btn as HTMLElement).dataset.hours || '6');
      loadChart();
    });
  });

  // Init ECharts
  initChart();

  // Initial load
  await Promise.all([loadSensors(), loadWeather(), loadIrrigationStatus(), loadChart()]);

  // Auto-refresh every 5 seconds
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = window.setInterval(() => {
    loadSensors();
    loadIrrigationStatus();
  }, 5000);

  // Expose control functions globally for inline onclick
  window._startIrrigation = startIrrigation;
  window._stopIrrigation = stopIrrigation;
  window._askAnalysis = () => {
    sessionStorage.setItem('pendingMsg', '分析当前土壤湿度数据，历史趋势和异常情况');
    window.location.hash = '#/agent';
  };
  window._askForecast = () => {
    sessionStorage.setItem('pendingMsg', '预测未来12小时土壤湿度变化');
    window.location.hash = '#/agent';
  };

  // Cleanup on page leave
  document.addEventListener('hashchange', () => {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
    if (chart) { chart.dispose(); chart = null; }
  }, { once: true });
}

function initChart() {
  const dom = document.getElementById('sensor-chart');
  if (!dom) return;
  chart = echarts.init(dom, 'dark');
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(14, 30, 64, 0.95)',
      borderColor: 'rgba(56, 189, 248, 0.3)',
      textStyle: { color: '#f0f6ff', fontSize: 12 },
    },
    legend: {
      data: ['土壤湿度 (%)', '温度 (°C)', '降雨 (mm/h)'],
      textStyle: { color: '#94a3b8', fontSize: 11 },
      top: 0,
    },
    grid: { left: 10, right: 10, top: 36, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category',
      data: [],
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisLabel: { color: '#475569', fontSize: 10, interval: 'auto' },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: { color: '#475569', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        name: '土壤湿度 (%)',
        type: 'line',
        data: [],
        smooth: true,
        lineStyle: { color: '#38bdf8', width: 2 },
        areaStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(56,189,248,0.25)' },
            { offset: 1, color: 'rgba(56,189,248,0)' }
          ])
        },
        symbol: 'none',
      },
      {
        name: '温度 (°C)',
        type: 'line',
        data: [],
        smooth: true,
        lineStyle: { color: '#f87171', width: 1.5 },
        symbol: 'none',
      },
      {
        name: '降雨 (mm/h)',
        type: 'bar',
        data: [],
        itemStyle: { color: 'rgba(129,140,248,0.6)' },
      },
    ],
  });

  window.addEventListener('resize', () => chart && chart.resize());
}

async function loadChart() {
  if (!chart) return;
  try {
    const [moisture, temp, rain] = await Promise.all([
      api.getSensorHistory('soil_moisture', currentHours),
      api.getSensorHistory('temperature', currentHours),
      api.getSensorHistory('rainfall', currentHours),
    ]);
    chart.setOption({
      xAxis: { data: moisture.timestamps },
      series: [
        { name: '土壤湿度 (%)', data: moisture.values },
        { name: '温度 (°C)', data: temp.values },
        { name: '降雨 (mm/h)', data: rain.values },
      ],
    });
  } catch (e) {
    console.error('Chart load failed:', e);
  }
}

async function loadSensors() {
  try {
    const data: any = await api.getCurrentSensors();
    const avg = data.average || {};

    const moisture: number = avg.soil_moisture ?? 0;
    const temp: number = avg.temperature ?? 0;
    const light: number = avg.light_intensity ?? 0;
    const rain: number = avg.rainfall ?? 0;

    // Update values
    setValue('val-moisture', moisture.toFixed(1));
    setValue('val-temp', temp.toFixed(1));
    setValue('val-light', Math.round(light).toString());
    setValue('val-rain', rain.toFixed(2));

    // Update trends
    const trendMoisture = prevMoisture !== null
      ? (moisture > prevMoisture ? `▲ +${(moisture - prevMoisture).toFixed(1)}%` : `▼ ${(moisture - prevMoisture).toFixed(1)}%`)
      : '─ 首次读数';
    setTrend('trend-moisture', trendMoisture, moisture > (prevMoisture ?? moisture));
    prevMoisture = moisture;

    setTrend('trend-temp', `${temp > 30 ? '▲ 偏热' : temp < 18 ? '▼ 偏冷' : '─ 适宜'}`, false);
    setTrend('trend-light', light > 600 ? '▲ 强光' : '─ 正常', light > 600);
    setTrend('trend-rain', rain > 1 ? '🌧️ 有雨' : '─ 无雨', false);

    // Status labels
    setStatus('status-moisture', moisture < 25 ? '⚠️ 严重缺水' : moisture < 40 ? '🟡 湿度偏低' : moisture < 70 ? '✅ 正常' : '💧 充足', moisture < 40);
    setStatus('status-temp', temp > 35 ? '⚠️ 超高温' : temp > 30 ? '🟡 偏热' : '✅ 适宜', temp > 35);
    setStatus('status-light', light < 100 ? '🌙 光照弱' : light > 800 ? '☀️ 强光' : '✅ 正常', false);
    setStatus('status-rain', rain > 2 ? '🌧️ 大雨中' : rain > 0.5 ? '🌦️ 有降雨' : '─ 无降雨', false);

    // Update timestamp
    const ts = document.getElementById('last-update');
    if (ts) ts.textContent = new Date().toLocaleTimeString('zh-CN');

  } catch (e) {
    console.error('Sensor load failed:', e);
  }
}

function setValue(id: string, val: string) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setTrend(id: string, text: string, isUp: boolean) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.style.background = isUp
    ? 'rgba(52, 211, 153, 0.1)' : 'rgba(248, 113, 113, 0.1)';
  el.style.color = isUp ? '#34d399' : '#f87171';
}

function setStatus(id: string, text: string, isWarn: boolean) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.style.color = isWarn ? '#fbbf24' : '#94a3b8';
}

async function loadWeather() {
  try {
    const data: any = await api.getWeather();
    const weatherEl = document.getElementById('weather-content');
    if (!weatherEl) return;

    const live = data.live || {};
    const forecast = data.forecast || [];

    let forecastHtml = forecast.map((d: any) => {
      const icon = getWeatherIcon(d.day_weather);
      const date = new Date(d.date);
      const dayName = date.toLocaleDateString('zh-CN', { weekday: 'short' });
      return `
        <div class="forecast-day">
          <div class="forecast-day-name">${dayName}</div>
          <div class="forecast-icon">${icon}</div>
          <div class="forecast-temp">${d.day_temp}°/${d.night_temp}°</div>
        </div>
      `;
    }).join('');

    weatherEl.innerHTML = `
      <div class="weather-current">
        <div class="weather-icon">${getWeatherIcon(live.weather)}</div>
        <div class="weather-main">
          <div class="weather-temp">${live.temperature}°C</div>
          <div class="weather-desc">${live.weather} · ${live.wind_direction}风 ${live.wind_power}级</div>
        </div>
      </div>
      <div class="weather-forecast">${forecastHtml}</div>
    `;
  } catch (e) {
    const el = document.getElementById('weather-content');
    if (el) el.innerHTML = '<div class="weather-loading">天气加载失败</div>';
  }
}

async function loadIrrigationStatus() {
  try {
    const state: any = await api.getIrrigationStatus();
    const badge = document.getElementById('device-badge');
    const statusEl = document.getElementById('device-status');
    const elapsedRow = document.getElementById('device-elapsed-row');
    const remainRow = document.getElementById('device-remain-row');
    const elapsedEl = document.getElementById('device-elapsed');
    const remainEl = document.getElementById('device-remain');

    const running = state.status === 'running';

    if (badge) {
      badge.textContent = running ? '▶ 运行中' : '⏹ 已停止';
      badge.className = 'device-status-badge' + (running ? ' running' : '');
    }
    if (statusEl) statusEl.textContent = running ? '运行中 🟢' : '已停止 ⏹';
    if (elapsedRow) elapsedRow.style.display = running ? '' : 'none';
    if (remainRow) remainRow.style.display = running ? '' : 'none';
    if (running) {
      if (elapsedEl) elapsedEl.textContent = `${state.elapsed_minutes ?? 0} 分钟`;
      if (remainEl) remainEl.textContent = `${state.remaining_minutes ?? 0} 分钟`;
    }
  } catch (e) {
    console.error('Irrigation status load failed:', e);
  }
}

async function startIrrigation() {
  try {
    const res: any = await api.controlIrrigation('start', 30);
    alert(res.message || '灌溉已启动');
    loadIrrigationStatus();
  } catch (e: any) {
    alert('启动失败: ' + e.message);
  }
}

async function stopIrrigation() {
  try {
    const res: any = await api.controlIrrigation('stop');
    alert(res.message || '灌溉已停止');
    loadIrrigationStatus();
  } catch (e: any) {
    alert('停止失败: ' + e.message);
  }
}
