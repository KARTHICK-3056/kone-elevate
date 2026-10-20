import { AlertTriangle, Inbox, RefreshCw, WifiOff } from 'lucide-react';
import { cx } from '../utils/formatters';

/**
 * User-facing error panel.
 *
 * Only the normalised message from the API client is rendered - never a raw
 * exception or stack trace.
 */
export default function ErrorMessage({ error, onRetry, title, className = '', compact = false }) {
  if (!error) return null;

  const offline = Boolean(error.offline) || error.code === 'network_error';
  const message = typeof error === 'string' ? error : error.message || 'Something went wrong.';
  const heading = title || (offline ? 'Backend unavailable' : 'Something went wrong');
  const Icon = offline ? WifiOff : AlertTriangle;

  if (compact) {
    return (
      <div
        role="alert"
        className={cx(
          'flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800',
          className,
        )}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{message}</span>
        {onRetry ? (
          <button type="button" onClick={onRetry} className="ml-auto text-xs font-semibold underline">
            Retry
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div
      role="alert"
      className={cx('card border-red-200 bg-red-50/60 p-6 text-red-900 animate-fade-in', className)}
    >
      <div className="flex items-start gap-4">
        <span className="rounded-lg bg-red-100 p-2.5 text-red-700">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="flex-1">
          <h3 className="text-base font-bold">{heading}</h3>
          <p className="mt-1 text-sm">{message}</p>

          {offline ? (
            <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs text-red-800/90">
              <li>
                Start the API:{' '}
                <code className="rounded bg-white/70 px-1 py-0.5 font-mono">
                  uvicorn app.main:app --reload
                </code>{' '}
                in <code className="font-mono">backend/</code>
              </li>
              <li>
                Or start everything with{' '}
                <code className="rounded bg-white/70 px-1 py-0.5 font-mono">docker compose up</code>
              </li>
              <li>
                Confirm it responds at{' '}
                <code className="rounded bg-white/70 px-1 py-0.5 font-mono">
                  http://localhost:8000/api/v1/health
                </code>
              </li>
            </ol>
          ) : null}

          {onRetry ? (
            <button type="button" onClick={onRetry} className="btn-secondary mt-4">
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Try again
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Friendly empty state for lists and tables. */
export function EmptyState({ title = 'Nothing here yet', description, action, icon: Icon = Inbox }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <span className="rounded-full bg-steel-100 p-4 text-steel-400">
        <Icon className="h-7 w-7" aria-hidden="true" />
      </span>
      <h3 className="text-base font-semibold text-navy-900">{title}</h3>
      {description ? <p className="max-w-md text-sm text-steel-500">{description}</p> : null}
      {action}
    </div>
  );
}

/** Small inline warning used for prototype/limitation notices. */
export function NoticeBanner({ children, tone = 'amber', icon: Icon = AlertTriangle }) {
  const tones = {
    amber: 'border-amber-200 bg-amber-50 text-amber-900',
    blue: 'border-blue-200 bg-blue-50 text-blue-900',
    steel: 'border-steel-200 bg-steel-100 text-steel-700',
  };
  return (
    <div className={cx('flex items-start gap-2 rounded-lg border px-3 py-2 text-xs', tones[tone])}>
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
