/**
 * HydroAgent — Hash Router
 */

type RouteHandler = () => void | Promise<void>;

const routes: Record<string, RouteHandler> = {};

export function register(hash: string, handler: RouteHandler): void {
  routes[hash] = handler;
}

export function navigate(hash: string): void {
  window.location.hash = hash;
}

export function init(): void {
  const resolve = () => {
    const hash = window.location.hash.slice(1) || '/dashboard';
    const handler = routes[hash] || routes['/dashboard'];
    if (handler) handler();

    // Update nav active state
    document.querySelectorAll('.nav-link').forEach((link) => {
      const el = link as HTMLElement;
      const linkPage = el.dataset.page;
      const active = Boolean(linkPage && hash.includes(linkPage));
      el.classList.toggle('active', active);
    });
  };

  window.addEventListener('hashchange', resolve);
  resolve(); // initial render
}
