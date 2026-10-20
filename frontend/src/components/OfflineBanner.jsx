import { useState } from 'react';
import { AlertTriangle, CloudOff, RefreshCw, Trash2, UploadCloud } from 'lucide-react';
import { useOfflineSync } from '../hooks/useOfflineSync';
import { removeEntry, retryEntry } from '../offline/outbox';
import { cx } from '../utils/formatters';

/**
 * The visible half of the offline write queue (see src/offline/outbox.js).
 * Mounted in both the authenticated app shell and the standalone QR-scan
 * passport view - a technician with no signal needs to see "this is queued,
 * not lost" in either context.
 */
export default function OfflineBanner() {
  const { isOnline, syncing, pendingCount, failedCount, outbox, syncNow } = useOfflineSync();
  const [expanded, setExpanded] = useState(false);

  if (isOnline && pendingCount === 0 && failedCount === 0) return null;

  const failed = outbox.filter((entry) => entry.status === 'failed');
  const pending = outbox.filter((entry) => entry.status === 'pending');

  return (
    <div className="no-print sticky top-0 z-40">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className={cx(
          'flex w-full items-center justify-center gap-2 px-4 py-2 text-xs font-semibold',
          !isOnline
            ? 'bg-amber-500 text-white'
            : failedCount > 0
              ? 'bg-red-600 text-white'
              : 'bg-navy-800 text-white',
        )}
      >
        {!isOnline ? (
          <>
            <CloudOff className="h-4 w-4" aria-hidden="true" />
            No connection - working offline.
            {pendingCount > 0 && ` ${pendingCount} change${pendingCount === 1 ? '' : 's'} queued.`}
          </>
        ) : syncing ? (
          <>
            <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
            Syncing {pendingCount} queued change{pendingCount === 1 ? '' : 's'}...
          </>
        ) : failedCount > 0 ? (
          <>
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            {failedCount} queued change{failedCount === 1 ? '' : 's'} could not be synced - review below.
          </>
        ) : (
          <>
            <UploadCloud className="h-4 w-4" aria-hidden="true" />
            {pendingCount} change{pendingCount === 1 ? '' : 's'} waiting to sync.
          </>
        )}
      </button>

      {expanded ? (
        <div className="max-h-64 overflow-y-auto border-b border-steel-200 bg-white shadow-elevated">
          {pending.length === 0 && failed.length === 0 ? (
            <p className="px-4 py-3 text-xs text-steel-500">Nothing queued.</p>
          ) : (
            <ul>
              {failed.map((entry) => (
                <li
                  key={entry.id}
                  className="flex items-center justify-between gap-3 border-b border-steel-100 px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-red-700">{entry.description}</p>
                    <p className="truncate text-xs text-steel-500">{entry.error}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => retryEntry(entry.id)}
                      className="rounded-md px-2 py-1 text-xs font-semibold text-navy-700 hover:bg-steel-100"
                    >
                      Retry
                    </button>
                    <button
                      type="button"
                      onClick={() => removeEntry(entry.id)}
                      className="rounded-md p-1.5 text-steel-500 hover:bg-steel-100"
                      aria-label="Discard queued change"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </li>
              ))}
              {pending.map((entry) => (
                <li key={entry.id} className="border-b border-steel-100 px-4 py-2.5 last:border-b-0">
                  <p className="truncate text-sm text-navy-900">{entry.description}</p>
                  <p className="text-xs text-steel-400">
                    Queued {new Date(entry.createdAt).toLocaleTimeString()}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {isOnline ? (
            <div className="border-t border-steel-200 px-4 py-2 text-right">
              <button
                type="button"
                onClick={syncNow}
                disabled={syncing || pending.length === 0}
                className="rounded-md bg-navy-800 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
              >
                Sync now
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
