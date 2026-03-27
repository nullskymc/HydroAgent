/**
 * Main Application Entry Point
 */
import { api } from './api';
import * as router from './router';
import * as dashboard from './pages/dashboard';
import * as agent from './pages/agent';
import * as history from './pages/history';
import * as settings from './pages/settings';

// Register routes
router.register('/dashboard', dashboard.render);
router.register('/agent', agent.render);
router.register('/history', history.render);
router.register('/settings', settings.render);

// Initialize application
async function bootstrap() {
  try {
    // Check system status
    const status: any = await api.getStatus();
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    
    if (status && status.status === 'online') {
      if (dot) dot.classList.remove('offline');
      if (text) text.textContent = `引擎就绪 (v${status.version})`;
    } else {
      throw new Error('Offline');
    }
  } catch (e) {
    console.warn('System might be offline', e);
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    if (dot) dot.classList.add('offline');
    if (text) text.textContent = '服务离线';
  }

  // Update clock
  setInterval(() => {
    const timeEl = document.getElementById('status-time');
    if (timeEl) {
      timeEl.textContent = new Date().toLocaleTimeString('zh-CN', { 
        hour: '2-digit', minute: '2-digit' 
      });
    }
  }, 1000);

  // Start router
  router.init();
}

bootstrap();
