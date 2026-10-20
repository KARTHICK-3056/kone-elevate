import { useState } from 'react';
import { Download, Link2, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react';
import { auditApi } from '../api/client';
import { useAuditLog } from '../hooks/useDashboard';
import AuditTimeline from '../components/AuditTimeline';
import StatCard from '../components/StatCard';
import Loading from '../components/Loading';
import ErrorMessage, { NoticeBanner } from '../components/ErrorMessage';
import { downloadBlob, formatNumber, humanise, shortHash } from '../utils/formatters';

const ENTITY_TYPES = ['component', 'recovery_item', 'service_demand', 'recovery_match'];
const ACTIONS = [
  'CREATE',
  'UPDATE',
  'DELETE',
  'PREDICT',
  'SERVICE_EVENT',
  'STATUS_CHANGE',
  'RECOVERY_LISTED',
  'DEMAND_CREATED',
  'MATCH_PROPOSED',
  'MATCH_ACCEPTED',
  'MATCH_REJECTED',
];

/** Audit chain browser with the integrity verification action. */
export default function AuditLog() {
  const {
    items,
    total,
    page,
    page_size: pageSize,
    pages,
    params,
    setParams,
    stats,
    verification,
    verify,
    verifying,
    loading,
    error,
    refresh,
  } = useAuditLog();
  const [exportError, setExportError] = useState(null);

  const update = (changes) => setParams((previous) => ({ ...previous, page: 1, ...changes }));

  const exportCsv = async () => {
    try {
      downloadBlob(await auditApi.exportCsv(), 'kone_elevate_audit_chain.csv');
    } catch (err) {
      setExportError(err);
    }
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">Audit Log</h1>
          <p className="mt-1 text-sm text-steel-500">
            Append-only, tamper-evident SHA-256 chain of every action in the platform.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-secondary" onClick={exportCsv}>
            <Download className="h-4 w-4" aria-hidden="true" />
            Export CSV
          </button>
          <button type="button" className="btn-secondary" onClick={refresh} disabled={loading}>
            <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            Refresh
          </button>
          <button type="button" className="btn-accent" onClick={verify} disabled={verifying}>
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {verifying ? 'Verifying...' : 'Verify audit integrity'}
          </button>
        </div>
      </header>

      {/* -------------------------------------------------- verification */}
      {verification ? (
        verification.valid ? (
          <div
            className="flex items-start gap-3 rounded-lg border-2 border-emerald-500 bg-emerald-50 px-4 py-3 text-emerald-900"
            role="status"
          >
            <ShieldCheck className="mt-0.5 h-6 w-6 shrink-0 text-emerald-600" aria-hidden="true" />
            <div>
              <p className="text-base font-extrabold uppercase tracking-wide">AUDIT CHAIN VALID</p>
              <p className="mt-0.5 text-sm">
                {formatNumber(verification.records_checked)} records checked. Every SHA-256 hash was
                recomputed from its stored content and matched.
              </p>
              {verification.head_hash ? (
                <p className="mt-1 font-mono text-[0.7rem] text-emerald-800">
                  Head hash {shortHash(verification.head_hash, 16, 12)}
                </p>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="safety-banner" role="alert">
            <ShieldAlert className="mt-0.5 h-6 w-6 shrink-0" aria-hidden="true" />
            <div>
              <p className="text-base font-extrabold uppercase tracking-wide">
                AUDIT CHAIN INVALID
              </p>
              <p className="mt-0.5 text-sm font-medium">{verification.message}</p>
              <p className="mt-1 text-xs font-normal">
                First failure at record #{verification.invalid_record} (position{' '}
                {verification.invalid_position}), reason: {humanise(verification.reason)}.
              </p>
            </div>
          </div>
        )
      ) : (
        <NoticeBanner tone="steel" icon={Link2}>
          Each record hashes its own content together with the hash of the record before it. Editing
          any historical snapshot breaks every hash that follows, which the verification endpoint
          detects. This is tamper evidence, not a blockchain: there is no distributed consensus.
        </NoticeBanner>
      )}

      {exportError ? <ErrorMessage error={exportError} compact /> : null}
      {error ? <ErrorMessage error={error} onRetry={refresh} /> : null}

      {/* -------------------------------------------------------- stats */}
      {stats ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Total audit records" value={formatNumber(stats.total_records)} />
          <StatCard
            label="Entity types tracked"
            value={Object.keys(stats.by_entity_type).length}
            hint={Object.keys(stats.by_entity_type).map(humanise).join(', ')}
          />
          <StatCard
            label="Distinct actions"
            value={Object.keys(stats.by_action).length}
            hint={`Most frequent: ${
              Object.entries(stats.by_action).sort((a, b) => b[1] - a[1])[0]?.[0] || '-'
            }`}
          />
          <StatCard
            label="Chain head"
            value={shortHash(stats.head_hash, 6, 4)}
            hint="SHA-256 hash of the newest record"
          />
        </div>
      ) : null}

      {/* ------------------------------------------------------- filters */}
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label" htmlFor="audit-entity">
            Entity type
          </label>
          <select
            id="audit-entity"
            className="select w-auto"
            value={params.entity_type || ''}
            onChange={(event) => update({ entity_type: event.target.value || undefined })}
          >
            <option value="">All entities</option>
            {ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {humanise(type)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="audit-action">
            Action
          </label>
          <select
            id="audit-action"
            className="select w-auto"
            value={params.action || ''}
            onChange={(event) => update({ action: event.target.value || undefined })}
          >
            <option value="">All actions</option>
            {ACTIONS.map((action) => (
              <option key={action} value={action}>
                {humanise(action)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="audit-page-size">
            Rows
          </label>
          <select
            id="audit-page-size"
            className="select w-auto"
            value={pageSize}
            onChange={(event) => update({ page_size: Number(event.target.value) })}
          >
            {[25, 50, 100, 200].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        <p className="ml-auto text-xs text-steel-500">
          {formatNumber(total)} records - newest first
        </p>
      </div>

      {/* -------------------------------------------------------- chain */}
      <section className="card overflow-hidden">
        {loading ? (
          <Loading label="Loading audit chain..." />
        ) : (
          <div className="px-4">
            <AuditTimeline entries={items} />
          </div>
        )}

        {!loading && items.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-steel-200 px-4 py-3">
            <p className="text-xs text-steel-500">
              Page {page} of {pages || 1}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={page <= 1}
                onClick={() => setParams((previous) => ({ ...previous, page: previous.page - 1 }))}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={page >= pages}
                onClick={() => setParams((previous) => ({ ...previous, page: previous.page + 1 }))}
              >
                Next
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
