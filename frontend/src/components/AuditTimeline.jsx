import { useState } from 'react';
import { ChevronDown, ChevronRight, Link2, ShieldCheck } from 'lucide-react';
import { cx, formatDateTime, humanise, shortHash } from '../utils/formatters';
import { EmptyState } from './ErrorMessage';

const ACTION_STYLE = {
  CREATE: 'bg-emerald-100 text-emerald-800',
  UPDATE: 'bg-blue-100 text-blue-800',
  DELETE: 'bg-red-100 text-red-800',
  PREDICT: 'bg-cyan-100 text-cyan-800',
  SERVICE_EVENT: 'bg-indigo-100 text-indigo-800',
  STATUS_CHANGE: 'bg-amber-100 text-amber-900',
  RECOVERY_LISTED: 'bg-teal-100 text-teal-800',
  DEMAND_CREATED: 'bg-violet-100 text-violet-800',
  MATCH_PROPOSED: 'bg-sky-100 text-sky-800',
  MATCH_ACCEPTED: 'bg-emerald-100 text-emerald-800',
  MATCH_REJECTED: 'bg-steel-200 text-steel-700',
};

/** One expandable audit-chain entry. */
function AuditRow({ entry, showEntity }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="border-b border-steel-100 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start gap-3 px-1 py-3 text-left transition-colors hover:bg-steel-50"
        aria-expanded={open}
      >
        <span className="mt-1 text-steel-400">
          {open ? (
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[0.7rem] text-steel-400">#{entry.id}</span>
            <span
              className={cx(
                'badge',
                ACTION_STYLE[entry.action] || 'bg-steel-100 text-steel-700',
              )}
            >
              {humanise(entry.action)}
            </span>
            {showEntity ? (
              <span className="font-mono text-xs text-navy-800">
                {entry.entity_type}:{entry.entity_id}
              </span>
            ) : null}
            <span className="text-xs text-steel-500">{formatDateTime(entry.timestamp)}</span>
            <span className="text-xs text-steel-400">by {entry.actor}</span>
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[0.65rem] text-steel-400">
            <Link2 className="h-3 w-3" aria-hidden="true" />
            <span title={entry.previous_hash}>prev {shortHash(entry.previous_hash)}</span>
            <span aria-hidden="true">-&gt;</span>
            <span className="text-accent-dark" title={entry.current_hash}>
              {shortHash(entry.current_hash)}
            </span>
          </div>
        </div>
      </button>

      {open ? (
        <div className="px-8 pb-4">
          <div className="space-y-2 rounded-lg bg-navy-950 p-3">
            <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-navy-300">
              Immutable snapshot
            </p>
            <pre className="max-h-64 overflow-auto font-mono text-[0.7rem] leading-relaxed text-navy-100">
              {JSON.stringify(entry.data_snapshot ?? {}, null, 2)}
            </pre>
          </div>
          <dl className="mt-2 grid gap-1 font-mono text-[0.65rem] text-steel-500 sm:grid-cols-2">
            <div>
              <dt className="inline font-sans font-semibold">Previous hash: </dt>
              <dd className="inline break-all">{entry.previous_hash}</dd>
            </div>
            <div>
              <dt className="inline font-sans font-semibold">Current hash: </dt>
              <dd className="inline break-all">{entry.current_hash}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </li>
  );
}

/** Chain of audit entries, newest first. */
export default function AuditTimeline({ entries = [], showEntity = true }) {
  if (!entries.length) {
    return (
      <EmptyState
        title="No audit records"
        description="Actions such as registering a component, running an assessment or accepting a match append entries here."
        icon={ShieldCheck}
      />
    );
  }

  return (
    <ul className="divide-y divide-steel-100">
      {entries.map((entry) => (
        <AuditRow key={entry.id} entry={entry} showEntity={showEntity} />
      ))}
    </ul>
  );
}
