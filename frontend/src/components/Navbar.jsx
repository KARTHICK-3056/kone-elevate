import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Bell, CircleDot, LogOut, Menu, Search, ShieldAlert, UserRound, X } from 'lucide-react';
import { componentsApi, platformApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { cx, humanise } from '../utils/formatters';
import { navItemFor } from './Sidebar';

/**
 * Top bar: mobile menu, global component search, backend/model status and a
 * user placeholder.
 *
 * The status pill is deliberately honest - it reports when the API is
 * unreachable or the model has not been trained, rather than hiding it.
 */
export default function Navbar({ onOpenSidebar, notifications = [] }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [health, setHealth] = useState({ state: 'checking' });
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const { pathname } = useLocation();
  const current = navItemFor(pathname);
  const { user, logout } = useAuth();
  const containerRef = useRef(null);
  const searchRef = useRef(null);

  // Opening the mobile search puts the cursor straight into it.
  useEffect(() => {
    if (mobileSearchOpen) searchRef.current?.focus();
  }, [mobileSearchOpen]);
  useEffect(() => setMobileSearchOpen(false), [pathname]);

  // -- backend + model status ---------------------------------------------
  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const data = await platformApi.health();
        if (!cancelled) {
          setHealth({
            state: data.model?.model_available ? 'ok' : 'degraded',
            version: data.version,
            model: data.model,
          });
        }
      } catch {
        if (!cancelled) setHealth({ state: 'offline' });
      }
    };

    check();
    const timer = setInterval(check, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  // -- debounced component search -----------------------------------------
  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      return undefined;
    }

    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await componentsApi.list({ search: term, page_size: 6 });
        setResults(data.items || []);
        setShowResults(true);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // -- close dropdowns on outside click -----------------------------------
  useEffect(() => {
    const onClick = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setShowResults(false);
        setShowNotifications(false);
        setShowProfile(false);
        setMobileSearchOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const openComponent = (componentId) => {
    setQuery('');
    setResults([]);
    setShowResults(false);
    setMobileSearchOpen(false);
    navigate(`/components/${componentId}`);
  };

  const statusStyle = {
    checking: { dot: 'text-steel-400', label: 'Checking...', chip: 'bg-steel-100 text-steel-600' },
    ok: { dot: 'text-emerald-500', label: 'API + model online', chip: 'bg-emerald-50 text-emerald-800' },
    degraded: { dot: 'text-amber-500', label: 'Model not trained', chip: 'bg-amber-50 text-amber-800' },
    offline: { dot: 'text-red-500', label: 'Backend offline', chip: 'bg-red-50 text-red-800' },
  }[health.state];

  return (
    <header
      ref={containerRef}
      className="no-print sticky top-0 z-30 border-b border-steel-200 bg-white/95 backdrop-blur"
    >
      <div className="relative flex h-16 items-center gap-2 px-3 sm:gap-3 sm:px-6">
        <button
          type="button"
          onClick={onOpenSidebar}
          className="rounded-lg p-2 text-steel-600 hover:bg-steel-100 lg:hidden"
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>

        <Link to="/" className="flex min-w-0 items-center gap-2 sm:w-44 sm:shrink-0 lg:hidden" aria-label="KONE ELEVATE - Dashboard">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-xs font-extrabold text-white">
            KE
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-bold text-navy-900">{current?.label || 'KONE ELEVATE'}</span>
            <span className="hidden text-[0.6rem] uppercase tracking-wider text-steel-500 min-[400px]:block">
              KONE ELEVATE
            </span>
          </span>
        </Link>

        {/* ------------------------------------------------------- search */}
        <button
          type="button"
          onClick={() => setMobileSearchOpen((value) => !value)}
          className="ml-auto rounded-lg p-2 text-steel-600 hover:bg-steel-100 sm:hidden"
          aria-label={mobileSearchOpen ? 'Close search' : 'Search components'}
          aria-expanded={mobileSearchOpen}
        >
          {mobileSearchOpen ? <X className="h-5 w-5" aria-hidden="true" /> : <Search className="h-5 w-5" aria-hidden="true" />}
        </button>
        <div
          className={cx(
            'w-full sm:relative sm:ml-auto sm:block sm:w-auto sm:max-w-md sm:flex-1 sm:border-0 sm:bg-transparent sm:p-0 lg:ml-0',
            mobileSearchOpen
              ? 'absolute inset-x-0 top-full block border-b border-steel-200 bg-white px-4 pb-3 pt-1 shadow-card'
              : 'hidden',
          )}
        >
          <div className="relative">
          <label htmlFor="global-search" className="sr-only">
            Search components
          </label>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-400"
            aria-hidden="true"
          />
          <input
            id="global-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={() => results.length && setShowResults(true)}
            placeholder="Search component id, serial or manufacturer..."
            className="input pl-9"
            autoComplete="off"
            ref={searchRef}
          />

          {showResults && (results.length > 0 || searching) ? (
            <div className="absolute left-0 right-0 top-full z-20 mt-1 overflow-hidden rounded-lg border border-steel-200 bg-white shadow-elevated">
              {searching ? (
                <p className="px-4 py-3 text-sm text-steel-500">Searching...</p>
              ) : (
                <ul className="max-h-80 overflow-y-auto">
                  {results.map((item) => (
                    <li key={item.component_id}>
                      <button
                        type="button"
                        onClick={() => openComponent(item.component_id)}
                        className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-steel-50"
                      >
                        <span>
                          <span className="block font-mono text-sm font-semibold text-navy-900">
                            {item.component_id}
                          </span>
                          <span className="block text-xs text-steel-500">
                            {item.component_type} - {item.serial_number}
                          </span>
                        </span>
                        {item.is_safety_critical ? (
                          <ShieldAlert className="h-4 w-4 shrink-0 text-red-500" aria-hidden="true" />
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
          </div>
        </div>

        <div className="flex items-center gap-1 sm:ml-auto sm:gap-2">
          {/* ------------------------------------------------ status pill */}
          <span
            className={cx(
              'hidden shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold lg:inline-flex',
              statusStyle.chip,
            )}
            title={
              health.model?.model_version
                ? `Model ${health.model.model_version}`
                : 'Backend health status'
            }
          >
            <CircleDot className={cx('h-3 w-3', statusStyle.dot)} aria-hidden="true" />
            {statusStyle.label}
          </span>

          {/* ------------------------------------------------ notifications */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowNotifications((value) => !value)}
              className="relative rounded-lg p-2 text-steel-600 hover:bg-steel-100"
              aria-label="Notifications"
            >
              <Bell className="h-5 w-5" aria-hidden="true" />
              {notifications.length ? (
                <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-dispose px-1 text-[0.6rem] font-bold text-white">
                  {notifications.length}
                </span>
              ) : null}
            </button>

            {showNotifications ? (
              <div className="absolute right-0 top-full z-20 mt-1 w-[min(20rem,calc(100vw-1.5rem))] overflow-hidden rounded-lg border border-steel-200 bg-white shadow-elevated">
                <p className="border-b border-steel-200 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-steel-500">
                  Attention required
                </p>
                {notifications.length ? (
                  <ul className="max-h-72 overflow-y-auto">
                    {notifications.map((note) => (
                      <li
                        key={note.id}
                        className="border-b border-steel-100 px-4 py-3 last:border-b-0"
                      >
                        <p className="text-sm font-semibold text-navy-900">{note.title}</p>
                        <p className="mt-0.5 text-xs text-steel-500">{note.description}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="px-4 py-6 text-center text-sm text-steel-400">Nothing needs attention.</p>
                )}
              </div>
            ) : null}
          </div>

          {/* ----------------------------------------------------- profile */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowProfile((value) => !value)}
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-steel-100"
              aria-label="Account menu"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-navy-800 text-white">
                <UserRound className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="hidden text-left lg:block">
                <span className="block text-xs font-semibold text-navy-900">
                  {user?.display_name || 'Signed in'}
                </span>
                <span className="block text-[0.65rem] text-steel-500">
                  {humanise(user?.role) || 'Loading...'}
                </span>
              </span>
            </button>

            {showProfile ? (
              <div className="absolute right-0 top-full z-20 mt-1 w-64 overflow-hidden rounded-lg border border-steel-200 bg-white shadow-elevated">
                <div className="border-b border-steel-200 px-4 py-3">
                  <p className="text-sm font-semibold text-navy-900">{user?.display_name}</p>
                  <p className="mt-0.5 break-all font-mono text-[0.7rem] text-steel-500">
                    {user?.email}
                  </p>
                  <p className="mt-1.5 inline-block rounded bg-navy-100 px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-navy-800">
                    {humanise(user?.role)}
                  </p>
                </div>
                <p className="px-4 py-2.5 text-[0.7rem] leading-relaxed text-steel-500">
                  Every change you make is recorded against this account in the audit
                  chain.
                </p>
                <button
                  type="button"
                  onClick={logout}
                  className="flex w-full items-center gap-2 border-t border-steel-200 px-4 py-2.5 text-left text-sm font-semibold text-red-700 hover:bg-red-50"
                >
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
