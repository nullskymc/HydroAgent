import { api } from '../api';

export async function render(): Promise<void> {
  const app = document.getElementById('app');
  const tpl = document.getElementById('tpl-settings') as HTMLTemplateElement;
  if (!app || !tpl) return;
  
  app.innerHTML = '';
  app.appendChild(tpl.content.cloneNode(true));

  bindRange('threshold-moisture', 'val-threshold-moisture', '%');
  bindRange('threshold-duration', 'val-threshold-duration', ' 分钟');
  bindRange('threshold-alarm', 'val-threshold-alarm', '%');
  bindToggle('toggle-alarm', 'alarm-status-text', '已启用', '已禁用');

  await loadSettings();

  const btnSave = document.getElementById('btn-save-settings');
  if (btnSave) btnSave.addEventListener('click', saveSettings);
}

function bindRange(inputId: string, valId: string, suffix: string): void {
  const input = document.getElementById(inputId) as HTMLInputElement;
  const val = document.getElementById(valId);
  if (!input || !val) return;
  input.addEventListener('input', () => { val.textContent = input.value + suffix; });
}

function bindToggle(inputId: string, textId: string, onText: string, offText: string): void {
  const input = document.getElementById(inputId) as HTMLInputElement;
  const text = document.getElementById(textId);
  if (!input || !text) return;
  input.addEventListener('change', () => {
    text.textContent = input.checked ? onText : offText;
    text.style.color = input.checked ? 'var(--brand-accent)' : 'var(--text-muted)';
  });
}

function setRangeVal(inputId: string, valId: string, value: number, suffix: string): void {
  const input = document.getElementById(inputId) as HTMLInputElement;
  const val = document.getElementById(valId);
  if (input && val && value !== undefined) {
    input.value = value.toString();
    val.textContent = value + suffix;
  }
}

function updateInfo(id: string, text: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

async function loadSettings(): Promise<void> {
  try {
    const s: any = await api.getSettings();
    setRangeVal('threshold-moisture', 'val-threshold-moisture', s.soil_moisture_threshold, '%');
    setRangeVal('threshold-duration', 'val-threshold-duration', s.default_duration_minutes, ' 分钟');
    setRangeVal('threshold-alarm', 'val-threshold-alarm', s.alarm_threshold, '%');

    const toggleInput = document.getElementById('toggle-alarm') as HTMLInputElement;
    const toggleText = document.getElementById('alarm-status-text');
    if (toggleInput && toggleText) {
      toggleInput.checked = s.alarm_enabled;
      toggleText.textContent = s.alarm_enabled ? '已启用' : '已禁用';
      toggleText.style.color = s.alarm_enabled ? 'var(--brand-accent)' : 'var(--text-muted)';
    }

    updateInfo('info-model', s.model_name || '未配置');
    updateInfo('info-db', (s.db_type || 'sqlite').toUpperCase());
    let sensorsStr = '--';
    if (Array.isArray(s.sensor_ids)) sensorsStr = s.sensor_ids.join(', ');
    else if (typeof s.sensor_ids === 'string') sensorsStr = s.sensor_ids;
    updateInfo('info-sensors', sensorsStr);
  } catch (e) {
    console.error('Failed to load settings:', e);
  }
}

async function saveSettings(): Promise<void> {
  const btn = document.getElementById('btn-save-settings') as HTMLButtonElement;
  const status = document.getElementById('save-status');
  if (!btn || !status) return;
  btn.disabled = true;
  status.textContent = '保存中...';
  status.style.color = 'var(--text-muted)';

  try {
    const moistureEl = document.getElementById('threshold-moisture') as HTMLInputElement;
    const durationEl = document.getElementById('threshold-duration') as HTMLInputElement;
    const alarmEl = document.getElementById('threshold-alarm') as HTMLInputElement;
    const toggleEl = document.getElementById('toggle-alarm') as HTMLInputElement;
    await api.updateSettings({
      soil_moisture_threshold: parseFloat(moistureEl.value),
      default_duration_minutes: parseInt(durationEl.value, 10),
      alarm_threshold: parseFloat(alarmEl.value),
      alarm_enabled: toggleEl.checked
    });
    status.textContent = '✅ 已保存';
    status.style.color = 'var(--brand-accent)';
  } catch (e: any) {
    status.textContent = '❌ 保存失败: ' + e.message;
    status.style.color = 'var(--brand-danger)';
  } finally {
    btn.disabled = false;
    setTimeout(() => { if (status.textContent?.includes('✅')) status.textContent = ''; }, 3000);
  }
}
