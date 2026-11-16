import { NavLink, Outlet } from 'react-router-dom';
import { Activity, Archive, ClipboardList, FileInput, LayoutDashboard, Settings2 } from 'lucide-react';
import { ToastProvider } from './Toast';

const navItems = [
  { to: '/', label: 'Dashboard', end: true, Icon: LayoutDashboard },
  { to: '/cases', label: 'Cases', end: false, Icon: ClipboardList },
  { to: '/ingest', label: 'Ingest', end: false, Icon: FileInput },
  { to: '/suppressed', label: 'Suppressed', end: false, Icon: Archive },
  { to: '/audit', label: 'Audit log', end: false, Icon: Activity },
  { to: '/settings', label: 'Settings', end: false, Icon: Settings2 },
];

const useMock = import.meta.env.VITE_USE_MOCK !== 'false';

export default function Layout() {
  return (
    <ToastProvider>
      <div className="flex min-h-screen flex-col bg-paper text-text">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-full focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-text"
        >
          Skip to content
        </a>
        <header className="sticky top-0 z-30 flex min-h-14 items-center justify-between border-b border-border bg-surface px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <span className="text-16 font-semibold tracking-heading">Prahari</span>
            <span className="rounded-full border border-border-strong px-2 py-0.5 text-12 font-medium text-text-secondary">{useMock ? 'Demo mode' : 'Connected'}</span>
          </div>
          <span className="flex items-center gap-2 text-13 text-text-secondary">
            <span aria-hidden="true" className={`h-2 w-2 rounded-full ${useMock ? 'bg-info' : 'bg-success'}`} />
            {useMock ? 'Mock data' : 'Live API'}
          </span>
        </header>

        <div className="flex flex-1 flex-col md:flex-row">
          <nav aria-label="Main" className="border-b border-border bg-surface md:w-56 md:shrink-0 md:border-b-0 md:border-r">
            <ul className="flex gap-1 overflow-x-auto p-2 md:sticky md:top-14 md:flex-col md:overflow-visible md:p-3">
              {navItems.map(({ to, label, end, Icon }) => (
                <li key={to} className="shrink-0">
                  <NavLink
                    to={to}
                    end={end}
                    className={({ isActive }) =>
                      `flex min-h-11 items-center gap-3 rounded-full px-3 py-2 text-13 transition-colors duration-micro ${
                        isActive
                          ? 'bg-text font-semibold text-primary-text'
                          : 'text-text-secondary hover:bg-sunken hover:text-text'
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${isActive ? 'bg-surface/15 text-primary-text' : 'bg-sunken text-text-secondary'}`}>
                          <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                        </span>
                        {label}
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex min-w-0 flex-1 flex-col">
            <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 p-4 sm:p-6 lg:p-8">
              <Outlet />
            </main>
            <footer className="border-t border-border px-4 py-3 text-12 text-text-muted sm:px-6">
              Simulated data. Not a compliance tool.
            </footer>
          </div>
        </div>
      </div>
    </ToastProvider>
  );
}
