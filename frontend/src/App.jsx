import { Component as ReactComponent, useEffect, useState } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import MobileNav from './components/MobileNav';
import { BackToTop, ScrollToTop } from './components/ScrollHelpers';
import OfflineBanner from './components/OfflineBanner';
import ErrorMessage from './components/ErrorMessage';
import Loading from './components/Loading';
import { AuthProvider, useAuth } from './context/AuthContext';
import Dashboard from './pages/Dashboard';
import Components from './pages/Components';
import ComponentDetails from './pages/ComponentDetails';
import ComponentPassport from './pages/ComponentPassport';
import Prediction from './pages/Prediction';
import Analytics from './pages/Analytics';
import Forecast from './pages/Forecast';
import Compliance from './pages/Compliance';
import Login from './pages/Login';
import AuditLog from './pages/AuditLog';
import Simulation from './pages/Simulation';
import NotFound from './pages/NotFound';
import { SYNTHETIC_DATA_NOTICE } from './utils/constants';

/**
 * Top-level error boundary.
 *
 * A rendering fault in one page must never leave the user staring at a blank
 * screen or a raw React stack trace. The fault is cleared when ``resetKey``
 * changes (the route), so one broken page does not take every other page
 * down with it.
 */
export class ErrorBoundary extends ReactComponent {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(previous) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error, info) {
    // Kept in the console for developers; users only see the friendly panel.
    console.error('Unhandled UI error:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6">
          <ErrorMessage
            title="This page could not be displayed"
            error={{
              message:
                'The interface hit an unexpected problem. Reload the page, and if it persists check the browser console for details.',
            }}
            onRetry={() => window.location.reload()}
          />
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const location = useLocation();

  // The public passport view is optimised for a phone that just scanned a QR
  // code: no chrome, no navigation, no sign-in. A technician in a basement
  // machine room has no login, and the backend keeps these endpoints public
  // to match. This deliberately sits outside the AuthProvider.
  const isStandalonePassport = /^\/passport\/[^/]+$/.test(location.pathname);

  if (isStandalonePassport) {
    return (
      <ErrorBoundary resetKey={location.pathname}>
        <OfflineBanner />
        <Routes>
          <Route path="/passport/:componentId" element={<ComponentPassport standalone />} />
        </Routes>
      </ErrorBoundary>
    );
  }

  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
}

/** The signed-in application shell. Renders the sign-in screen until there is a user. */
const COLLAPSE_KEY = 'kone-elevate.sidebar-collapsed';

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  } catch {
    return false;
  }
}

function AuthenticatedApp() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const { isAuthenticated, loading } = useAuth();
  const { pathname } = useLocation();

  const toggleCollapsed = () =>
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, value ? '0' : '1');
      } catch {
        // A per-viewer convenience only; the layout works without it.
      }
      return !value;
    });

  // The mobile drawer closes on navigation and on Escape.
  useEffect(() => setSidebarOpen(false), [pathname]);
  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const onKey = (event) => event.key === 'Escape' && setSidebarOpen(false);
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [sidebarOpen]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-steel-50">
        <Loading label="Restoring your session..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <ErrorBoundary>
        <Login />
      </ErrorBoundary>
    );
  }

  return (
    <div className="flex min-h-screen bg-steel-50">
      <ScrollToTop />
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <OfflineBanner />
        <Navbar onOpenSidebar={() => setSidebarOpen(true)} />

        <main className="mx-auto w-full max-w-[1760px] flex-1 px-4 pb-8 pt-5 sm:px-6 sm:pt-6 lg:px-8">
          <ErrorBoundary resetKey={pathname}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/components" element={<Components />} />
              <Route path="/components/:componentId" element={<ComponentDetails />} />
              <Route path="/passport" element={<ComponentPassport />} />
              <Route path="/prediction" element={<Prediction />} />
              <Route path="/prediction/:componentId" element={<Prediction />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/forecast" element={<Forecast />} />
              <Route path="/simulation" element={<Simulation />} />
              <Route path="/compliance" element={<Compliance />} />
              <Route path="/audit" element={<AuditLog />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </ErrorBoundary>
        </main>

        <footer className="no-print mb-16 border-t border-steel-200 bg-white px-4 py-4 text-center sm:px-6 lg:mb-0">
          <p className="text-xs text-steel-500">{SYNTHETIC_DATA_NOTICE}</p>
          <p className="mt-1 text-[0.65rem] text-steel-400">
            KONE ELEVATE prototype - Team CodeFather, SRM Institute of Science and Technology,
            Ramapuram. Independent student project; not affiliated with or endorsed by KONE
            Corporation.
          </p>
        </footer>
      </div>

      <MobileNav onOpenMore={() => setSidebarOpen(true)} />
      <BackToTop />
    </div>
  );
}
