import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Filter, RefreshCw, RotateCcw, ShieldAlert } from 'lucide-react';
import { useAnalytics } from '../hooks/useDashboard';
import { useComponentFilters } from '../hooks/useComponents';
import { useCalibration } from '../hooks/usePrediction';
import Loading from '../components/Loading';
import ErrorMessage from '../components/ErrorMessage';
import StatCard from '../components/StatCard';
import ImpactCard, { ImpactAssumptions } from '../components/ImpactCard';
import {
  ComponentTypeChart,
  ConfidenceChart,
  DispositionChart,
  FeatureImportanceChart,
  HealthBandRadar,
  HealthDistributionChart,
  LifecycleChart,
  MonthlyActivityChart,
  RecoveryValueChart,
  ReliabilityDiagramChart,
} from '../components/Charts';
import { RecommendationBadge } from '../components/HealthBadge';
import { COMPONENT_TYPES, LIFECYCLE_STATUSES } from '../utils/constants';
import { formatCurrency, formatDate, formatNumber, humanise } from '../utils/formatters';

/** Fleet-level analytics with filters, impact model and the safety queue. */
export default function Analytics() {
  const { analytics, filters, setFilters, loading, error, refresh } = useAnalytics();
  const filterOptions = useComponentFilters();
  const { calibration } = useCalibration();
  const [showFilters, setShowFilters] = useState(false);

  if (loading && !analytics) return <Loading label="Building fleet analytics..." />;
  if (error && !analytics) return <ErrorMessage error={error} onRetry={refresh} />;
  if (!analytics) return null;

  const { summary, impact } = analytics;
  const symbol = impact?.currency_symbol || 'Rs.';

  const setFilter = (key, value) =>
    setFilters((previous) => {
      const next = { ...previous };
      if (!value || (Array.isArray(value) && !value.length)) delete next[key];
      else next[key] = value;
      return next;
    });

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">Analytics</h1>
          <p className="mt-1 text-sm text-steel-500">
            Fleet-level condition, recommendation categories and recovery potential.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setShowFilters((value) => !value)}
          >
            <Filter className="h-4 w-4" aria-hidden="true" />
            Filters
            {Object.keys(filters).length ? (
              <span className="ml-1 rounded-full bg-accent px-1.5 text-[0.65rem] text-white">
                {Object.keys(filters).length}
              </span>
            ) : null}
          </button>
          <button type="button" className="btn-secondary" onClick={refresh} disabled={loading}>
            <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      {showFilters ? (
        <div className="card grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="label" htmlFor="filter-type">
              Component type
            </label>
            <select
              id="filter-type"
              className="select"
              value={filters.component_type?.[0] || ''}
              onChange={(event) =>
                setFilter('component_type', event.target.value ? [event.target.value] : null)
              }
            >
              <option value="">All types</option>
              {COMPONENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="filter-status">
              Lifecycle status
            </label>
            <select
              id="filter-status"
              className="select"
              value={filters.current_status?.[0] || ''}
              onChange={(event) =>
                setFilter('current_status', event.target.value ? [event.target.value] : null)
              }
            >
              <option value="">All statuses</option>
              {LIFECYCLE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {humanise(status)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="filter-location">
              Location
            </label>
            <select
              id="filter-location"
              className="select"
              value={filters.location || ''}
              onChange={(event) => setFilter('location', event.target.value)}
            >
              <option value="">All locations</option>
              {filterOptions.locations.map((location) => (
                <option key={location} value={location}>
                  {location}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="filter-from">
              Installed from
            </label>
            <input
              id="filter-from"
              type="date"
              className="input"
              value={filters.installed_from || ''}
              onChange={(event) => setFilter('installed_from', event.target.value)}
            />
          </div>

          <div>
            <label className="label" htmlFor="filter-to">
              Installed to
            </label>
            <input
              id="filter-to"
              type="date"
              className="input"
              value={filters.installed_to || ''}
              onChange={(event) => setFilter('installed_to', event.target.value)}
            />
            <button type="button" className="btn-ghost btn-sm mt-2" onClick={() => setFilters({})}>
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Clear
            </button>
          </div>
        </div>
      ) : null}

      {/* ------------------------------------------------------ headline */}
      <div id="an-kpis" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard label="Components in scope" value={formatNumber(summary.total_components)} />
        <StatCard label="Assessed by AI" value={formatNumber(summary.assessed_components)} />
        <StatCard
          label="Average health"
          value={summary.average_health_score.toFixed(1)}
          unit="/100"
        />
        <StatCard
          label="Safety-critical"
          value={formatNumber(summary.safety_critical_components)}
          hint={`${formatNumber(summary.components_awaiting_inspection)} awaiting inspection`}
          tone="warning"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        <StatCard
          label="Recovery potential"
          value={formatCurrency(impact.total_recovery_value, symbol)}
          hint={`${impact.avoided_procurement_share_percent}% of new-part cost`}
          tone="continue"
          estimate
        />
        <StatCard
          label="Diverted from disposal"
          value={formatNumber(impact.components_diverted_from_disposal)}
          hint={`${impact.diversion_rate_percent}% diversion rate`}
          tone="component"
          estimate
        />
        <StatCard
          label="Component recovery demand"
          value={formatNumber(summary.component_recovery)}
          hint="Components assessed as Component Recovery"
          tone="navy"
        />
      </div>

      {/* -------------------------------------------------------- charts */}
      <div id="an-charts" className="grid scroll-mt-32 grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        <DispositionChart data={analytics.disposition.items} />
        <HealthDistributionChart data={analytics.health.buckets} />
        <ComponentTypeChart data={analytics.component_types.items} />
        <HealthBandRadar data={analytics.health.bands} />
        <LifecycleChart data={analytics.lifecycle.items} />
        <ConfidenceChart data={analytics.confidence.buckets} />
        <RecoveryValueChart data={analytics.recovery_value_by_type} currencySymbol={symbol} />
        <MonthlyActivityChart data={analytics.monthly_activity.items} />
        <FeatureImportanceChart data={analytics.feature_importance} />
      </div>

      {/* --------------------------------------------- model credibility */}
      {calibration?.model_available ? (
        <div id="an-model" className="scroll-mt-32 space-y-5">
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatCard
              label="Calibration error (ECE)"
              value={calibration.reliability?.expected_calibration_error?.toFixed(3) ?? '--'}
              hint={`${calibration.calibration_method} calibration, ${calibration.calibration_cv_folds}-fold`}
              tone="navy"
            />
            <StatCard
              label="Abstention rate"
              value={`${((calibration.abstention?.abstention_rate ?? 0) * 100).toFixed(1)}%`}
              hint="Flagged DEFER_TO_INSPECTION instead of guessing"
              tone="warning"
            />
            <StatCard
              label="Accuracy when it answers"
              value={`${((calibration.abstention?.accuracy_on_answered_subset ?? 0) * 100).toFixed(1)}%`}
              hint={`vs ${((calibration.abstention?.accuracy_without_abstention ?? 0) * 100).toFixed(1)}% answering everything`}
              tone="continue"
            />
            <StatCard
              label="Conformal coverage target"
              value={`${((calibration.conformal?.target_coverage ?? 0) * 100).toFixed(0)}%`}
              hint={`q_hat = ${calibration.conformal?.q_hat ?? '--'}`}
              tone="accent"
            />
          </div>
          <ReliabilityDiagramChart bins={calibration.reliability?.bins} />
        </div>
      ) : null}

      {/* -------------------------------------------------------- impact */}
      <div id="an-impact" className="scroll-mt-32 space-y-5">
        <ImpactCard impact={impact} title="Sustainability summary" />
        <ImpactAssumptions constants={impact.constants} />
      </div>

      {/* -------------------------------------------------- safety queue */}
      <section id="an-safety" className="card scroll-mt-32">
        <header className="card-header">
          <div>
            <h2 className="card-title">
              <ShieldAlert className="mr-1.5 inline h-4 w-4 text-dispose" aria-hidden="true" />
              Safety-critical inspection queue
            </h2>
            <p className="mt-0.5 text-xs text-steel-500">
              Steel ropes and overspeed governors (and any brakes on record) always require human
              inspection, whatever the AI recommends.
            </p>
          </div>
        </header>
        <div className="max-h-96 overflow-y-auto">
          {analytics.safety_queue.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Type</th>
                  <th>Location</th>
                  <th className="text-right">Health</th>
                  <th>AI recommendation</th>
                  <th>Status</th>
                  <th>Last service</th>
                  <th>Requirement</th>
                </tr>
              </thead>
              <tbody>
                {analytics.safety_queue.map((entry) => (
                  <tr key={entry.component_id}>
                    <td>
                      <Link
                        to={`/passport/${entry.component_id}`}
                        className="font-mono text-xs font-semibold text-navy-900 hover:text-accent"
                      >
                        {entry.component_id}
                      </Link>
                    </td>
                    <td className="text-sm">{entry.component_type}</td>
                    <td className="text-xs">{entry.location || '-'}</td>
                    <td className="text-right font-mono text-sm">
                      {entry.health_score?.toFixed(0) ?? '--'}
                    </td>
                    <td>
                      <RecommendationBadge recommendation={entry.recommendation} size="sm" />
                    </td>
                    <td className="text-xs">{humanise(entry.current_status)}</td>
                    <td className="text-xs">{formatDate(entry.last_service_date)}</td>
                    <td>
                      <span className="badge bg-red-100 text-red-800">{entry.safety_message}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="px-5 py-10 text-center text-sm text-steel-400">
              No safety-critical components in scope for the current filters.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
