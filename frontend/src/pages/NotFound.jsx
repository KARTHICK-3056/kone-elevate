import { Link } from 'react-router-dom';
import { Compass, LayoutDashboard, QrCode } from 'lucide-react';
import { NAV_ITEMS } from '../components/Sidebar';

/** 404 page with a route directory so nobody hits a dead end. */
export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-5 py-16 text-center">
      <span className="rounded-full bg-steel-100 p-5 text-steel-400">
        <Compass className="h-10 w-10" aria-hidden="true" />
      </span>

      <div>
        <p className="font-mono text-sm font-bold text-accent">404</p>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-navy-900">
          That page does not exist
        </h1>
        <p className="mt-2 text-sm text-steel-500">
          The link may be out of date, or the component identifier in it may have been removed.
        </p>
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        <Link to="/" className="btn-accent">
          <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
          Go to dashboard
        </Link>
        <Link to="/passport" className="btn-secondary">
          <QrCode className="h-4 w-4" aria-hidden="true" />
          Look up a passport
        </Link>
      </div>

      <nav className="w-full border-t border-steel-200 pt-5">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-steel-500">
          All sections
        </p>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <Link
                to={item.to}
                className="flex flex-col items-center gap-1.5 rounded-lg border border-steel-200 bg-white p-3 text-xs font-medium text-steel-600 hover:border-accent hover:text-navy-900"
              >
                <item.icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
