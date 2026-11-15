import { NavLink, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/cases', label: 'Cases', end: false },
  { to: '/ingest', label: 'Ingest', end: false },
  { to: '/suppressed', label: 'Suppressed', end: false },
  { to: '/audit', label: 'Audit log', end: false },
  { to: '/settings', label: 'Settings', end: false },
];

const useMock = import.meta.env.VITE_USE_MOCK !== 'false';

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-paper text-text">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-sm focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-text"
      >
        Skip to content
      </a>

      <header className="flex h-12 items-center justify-between border-b border-border bg-surface px-4">
        <div className="flex items-center gap-3">
          <span className="text-16 font-semibold tracking-heading">Prahari</span>
          <span className="rounded-full border border-border-strong px-2 py-0.5 text-12 font-medium uppercase tracking-label text-text-secondary">
            Demo mode
          </span>
        </div>
        <span className="flex items-center gap-2 text-13 text-text-secondary">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-info" />
          {useMock ? 'Mock data' : 'Live API'}
        </span>
      </header>

      <div className="flex flex-1">
        <nav aria-label="Main" className="w-56 shrink-0 border-r border-border bg-surface p-3">
          <ul className="flex flex-col gap-1">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `block rounded-sm border-l-2 px-3 py-2 text-14 transition-colors duration-micro ${
                      isActive
                        ? 'border-primary bg-sunken font-medium text-text'
                        : 'border-transparent text-text-secondary hover:bg-sunken hover:text-text'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          <main id="main" className="flex-1 p-6">
            <Outlet />
          </main>
          <footer className="border-t border-border px-6 py-3 text-12 text-text-muted">
            Simulated data. Not a compliance tool.
          </footer>
        </div>
      </div>
    </div>
  );
}