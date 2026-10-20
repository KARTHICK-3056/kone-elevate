import { NavLink } from 'react-router-dom';
import {
  BarChart3,
  Box,
  Boxes,
  Brain,
  CalendarClock,
  FileCheck2,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
  X,
} from 'lucide-react';
import { cx } from '../utils/formatters';

/** Primary navigation, grouped cleanly by operational domain. */
export const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [
      { to: '/', label: 'Dashboard', short: 'Home', icon: LayoutDashboard, end: true, description: 'Portfolio status at a glance' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { to: '/components', label: 'Components', short: 'Parts', icon: Boxes, description: 'Registry, passport and parts management' },
      { to: '/prediction', label: 'AI Prediction', short: 'Predict', icon: Brain, description: 'Diagnostic AI assessment' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { to: '/analytics', label: 'Analytics', short: 'Analytics', icon: BarChart3, description: 'Fleet condition and recovery analytics' },
      { to: '/forecast', label: 'Forecast', short: 'Forecast', icon: CalendarClock, description: 'End-of-life and workshop capacity' },
      { to: '/simulation', label: 'Simulation', short: 'Simulate', icon: Box, description: 'What-if lift load simulation' },
    ],
  },
  {
    label: 'Governance',
    items: [
      { to: '/compliance', label: 'Compliance', short: 'Compliance', icon: FileCheck2, description: 'ESRS and BRSR disclosures' },
      { to: '/audit', label: 'Audit Log', short: 'Audit', icon: ShieldCheck, description: 'Tamper-evident SHA-256 chain' },
    ],
  },
];

export const NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);

/** The nav entry a pathname belongs to (detail pages map to their section). */
export function navItemFor(pathname) {
  if (pathname === '/') return NAV_ITEMS[0];
  if (pathname.startsWith('/passport')) return NAV_ITEMS.find((item) => item.to === '/components') || null;
  return NAV_ITEMS.find((item) => item.to !== '/' && pathname.startsWith(item.to)) || null;
}

function NavItem({ item, collapsed, onNavigate }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      title={collapsed ? `${item.label} - ${item.description}` : item.description}
      className={({ isActive }) =>
        cx(
          'group flex items-center rounded-lg text-sm font-medium transition-colors',
          collapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2',
          isActive
            ? 'bg-accent/15 text-white ring-1 ring-inset ring-accent/40'
            : 'text-navy-200 hover:bg-navy-800 hover:text-white',
        )
      }
    >
      <item.icon className="shrink-0" style={{ width: 18, height: 18 }} aria-hidden="true" />
      <span className={collapsed ? 'sr-only' : 'truncate'}>{item.label}</span>
    </NavLink>
  );
}

function SidebarContent({ collapsed = false, onNavigate, onClose, onToggleCollapsed }) {
  return (
    <div className="flex h-full flex-col bg-navy-950 text-navy-100">
      <div
        className={cx(
          'flex h-16 items-center border-b border-navy-800',
          collapsed ? 'justify-center px-2' : 'justify-between gap-3 px-5',
        )}
      >
        <NavLink to="/" className="flex min-w-0 items-center gap-3" onClick={onNavigate} title="KONE ELEVATE - Dashboard">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent font-extrabold text-white">
            KE
          </span>
          {collapsed ? null : (
            <span className="min-w-0">
              <span className="block truncate text-sm font-extrabold uppercase tracking-widest text-white">
                KONE ELEVATE
              </span>
              <span className="block truncate text-[0.6rem] uppercase tracking-wider text-navy-300">
                Component Passport
              </span>
            </span>
          )}
        </NavLink>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-navy-300 hover:bg-navy-800 hover:text-white"
            aria-label="Close navigation"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        ) : null}
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Main navigation">
        {NAV_GROUPS.map((group, index) => (
          <div key={group.label} className={index ? 'mt-4' : ''}>
            {collapsed ? (
              index ? <div className="mx-2 mb-3 border-t border-navy-800" aria-hidden="true" /> : null
            ) : (
              <p className="mb-1 px-3 text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-navy-400">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavItem key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className={cx('space-y-2 border-t border-navy-800 py-3', collapsed ? 'px-2' : 'px-4')}>
        {collapsed ? null : (
          <div className="rounded-lg bg-navy-900/60 px-3 py-2 text-[0.65rem] text-navy-300">
            <span className="font-semibold text-white">KONE ELEVATE</span>
            <p className="mt-0.5 text-[0.6rem] text-navy-400">Advisory Circular Intelligence</p>
          </div>
        )}
        {onToggleCollapsed ? (
          <button
            type="button"
            onClick={onToggleCollapsed}
            className={cx(
              'flex w-full items-center rounded-lg py-2 text-xs font-medium text-navy-300 hover:bg-navy-800 hover:text-white',
              collapsed ? 'justify-center' : 'gap-2 px-3',
            )}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
            ) : (
              <>
                <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
                Collapse sidebar
              </>
            )}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Primary navigation. A fixed sidebar on desktop that can collapse to an icon
 * rail (more room on wide screens), and a slide-over drawer on mobile.
 */
export default function Sidebar({ open, onClose, collapsed, onToggleCollapsed }) {
  return (
    <>
      <aside
        className={cx(
          'no-print hidden shrink-0 transition-[width] duration-200 lg:block',
          collapsed ? 'w-[76px]' : 'w-64',
        )}
      >
        <div className={cx('fixed inset-y-0 left-0 z-30 transition-[width] duration-200', collapsed ? 'w-[76px]' : 'w-64')}>
          <SidebarContent collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
        </div>
      </aside>

      {open ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-navy-950/60 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] animate-fade-in shadow-elevated">
            <SidebarContent onNavigate={onClose} onClose={onClose} />
          </div>
        </div>
      ) : null}
    </>
  );
}
