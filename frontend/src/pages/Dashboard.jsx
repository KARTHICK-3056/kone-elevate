import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Boxes,
  Coins,
  HeartPulse,
  PackageSearch,
  Recycle,
  RefreshCw,
  Repeat,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import StatCard from '../components/StatCard';
import { StatSkeleton } from '../components/Loading';
import ErrorMessage from '../components/ErrorMessage';
import {
  DispositionChart,
  HealthDistributionChart,
} from '../components/Charts';
import { useDashboard } from '../hooks/useDashboard';
import { useRecentPredictions } from '../hooks/usePrediction';
import { RecommendationBadge } from '../components/HealthBadge';
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
} from '../utils/formatters';
import { RECOMMENDATION_LABELS } from '../utils/constants';

/** Clean, minimal portfolio executive overview. */
export default function Dashboard() {
  const dashboard = useDashboard();
  const { items: recent } = useRecentPredictions(6);
  const { summary, loading, error, refresh } = dashboard;

  if (error && !summary) {
    return <ErrorMessage error={error} onRetry={refresh} title="Dashboard unavailable" />;
  }

  const symbol = summary?.currency_symbol || 'Rs.';

  return (
    <div className="space-y-6">
      {/* -------------------------------------------------------- Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">
            Portfolio Dashboard
          </h1>
          <p className="mt-1 text-sm text-steel-500">
            Real-time circular-economy status across monitored elevator components.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            className="btn-secondary"
            disabled={loading}
            title="Refresh dashboard metrics"
          >
            <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            Refresh
          </button>
          <Link to="/prediction" className="btn-accent">
            Run AI assessment
          </Link>
        </div>
      </header>

      {/* ------------------------------------------------- Executive KPIs */}
      {loading && !summary ? (
        <StatSkeleton count={4} />
      ) : summary ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Fleet Health Score"
              value={summary.average_health_score.toFixed(1)}
              unit="/100"
              hint="Transparent degradation model"
              icon={HeartPulse}
              tone="accent"
            />
            <StatCard
              label="Total Components"
              value={formatNumber(summary.total_components)}
              hint={`${formatNumber(summary.assessed_components)} assessed by AI`}
              icon={Boxes}
              tone="navy"
              to="/components"
            />
            <StatCard
              label="Potential Recovery Value"
              value={formatCurrency(summary.potential_recovery_value, symbol)}
              hint="Retained circular value"
              icon={Coins}
              tone="continue"
              estimate
            />
            <StatCard
              label="Awaiting Inspection"
              value={formatNumber(summary.components_awaiting_inspection)}
              hint="Safety-critical sign-off required"
              icon={ShieldAlert}
              tone="warning"
              to="/analytics#an-safety"
            />
          </div>

          {/* ----------------------------------- Circular Pathways Quickstrip */}
          <section className="card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-xs font-bold uppercase tracking-wider text-steel-500">
                Circular Disposition Pathways
              </h2>
              <Link
                to="/components"
                className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline"
              >
                View registry <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Link
                to="/components?recommendation=CONTINUE_USING"
                className="group rounded-lg border border-steel-200/80 bg-steel-50/50 p-3 transition hover:border-continue/50 hover:bg-continue/5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-steel-600">
                    {RECOMMENDATION_LABELS.CONTINUE_USING}
                  </span>
                  <Repeat className="h-4 w-4 text-continue transition group-hover:scale-110" aria-hidden="true" />
                </div>
                <p className="mt-2 font-mono text-xl font-bold text-navy-900">
                  {formatNumber(summary.continue_using)}
                </p>
                <p className="text-[0.7rem] text-steel-500">
                  {summary.total_components
                    ? formatPercent(summary.continue_using / summary.total_components, 0)
                    : '-'} of fleet
                </p>
              </Link>

              <Link
                to="/components?recommendation=COMPONENT_RECOVERY"
                className="group rounded-lg border border-steel-200/80 bg-steel-50/50 p-3 transition hover:border-component/50 hover:bg-component/5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-steel-600">
                    {RECOMMENDATION_LABELS.COMPONENT_RECOVERY}
                  </span>
                  <PackageSearch className="h-4 w-4 text-component transition group-hover:scale-110" aria-hidden="true" />
                </div>
                <p className="mt-2 font-mono text-xl font-bold text-navy-900">
                  {formatNumber(summary.component_recovery)}
                </p>
                <p className="text-[0.7rem] text-steel-500">
                  {summary.total_components
                    ? formatPercent(summary.component_recovery / summary.total_components, 0)
                    : '-'} of fleet
                </p>
              </Link>

              <Link
                to="/components?recommendation=MATERIAL_RECOVERY"
                className="group rounded-lg border border-steel-200/80 bg-steel-50/50 p-3 transition hover:border-material/50 hover:bg-material/5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-steel-600">
                    {RECOMMENDATION_LABELS.MATERIAL_RECOVERY}
                  </span>
                  <Recycle className="h-4 w-4 text-material transition group-hover:scale-110" aria-hidden="true" />
                </div>
                <p className="mt-2 font-mono text-xl font-bold text-navy-900">
                  {formatNumber(summary.material_recovery)}
                </p>
                <p className="text-[0.7rem] text-steel-500">
                  {summary.total_components
                    ? formatPercent(summary.material_recovery / summary.total_components, 0)
                    : '-'} of fleet
                </p>
              </Link>

              <Link
                to="/components?recommendation=DISPOSE"
                className="group rounded-lg border border-steel-200/80 bg-steel-50/50 p-3 transition hover:border-dispose/50 hover:bg-dispose/5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-steel-600">
                    {RECOMMENDATION_LABELS.DISPOSE}
                  </span>
                  <Trash2 className="h-4 w-4 text-dispose transition group-hover:scale-110" aria-hidden="true" />
                </div>
                <p className="mt-2 font-mono text-xl font-bold text-navy-900">
                  {formatNumber(summary.disposal)}
                </p>
                <p className="text-[0.7rem] text-steel-500">
                  {summary.total_components
                    ? formatPercent(summary.disposal / summary.total_components, 0)
                    : '-'} of fleet
                </p>
              </Link>
            </div>
          </section>

          {/* --------------------------------- Primary Executive Overview Charts */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <DispositionChart data={dashboard.disposition?.items || []} />
            <HealthDistributionChart data={dashboard.health?.buckets || []} />
          </div>

          {/* ---------------------------------- Immediate Action Center (2 cols) */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {/* Safety-Critical Queue */}
            <section className="card">
              <header className="card-header">
                <div>
                  <h2 className="card-title">Safety-Critical Attention Queue</h2>
                  <p className="mt-0.5 text-xs text-steel-500">
                    Components requiring human engineer inspection before action.
                  </p>
                </div>
                <Link to="/analytics#an-safety" className="btn-ghost btn-sm">
                  View all in Analytics
                </Link>
              </header>
              <div className="max-h-80 overflow-y-auto">
                {dashboard.safetyQueue?.length ? (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Component</th>
                        <th>Type</th>
                        <th className="text-right">Health</th>
                        <th>AI Recommendation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.safetyQueue.slice(0, 5).map((entry) => (
                        <tr key={entry.component_id}>
                          <td>
                            <Link
                              to={`/components/${entry.component_id}`}
                              className="font-mono text-xs font-semibold text-navy-900 hover:text-accent"
                            >
                              {entry.component_id}
                            </Link>
                          </td>
                          <td className="text-sm">{entry.component_type}</td>
                          <td className="text-right font-mono text-sm">
                            {entry.health_score?.toFixed(0) ?? '--'}
                          </td>
                          <td>
                            <RecommendationBadge recommendation={entry.recommendation} size="sm" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="px-5 py-8 text-center text-sm text-steel-400">
                    No safety-critical components currently awaiting inspection.
                  </p>
                )}
              </div>
            </section>

            {/* Recent Assessments Feed */}
            <section className="card">
              <header className="card-header">
                <div>
                  <h2 className="card-title">Recent AI Assessments</h2>
                  <p className="mt-0.5 text-xs text-steel-500">Latest advisory decisions recorded.</p>
                </div>
                <Link to="/prediction" className="btn-ghost btn-sm">
                  New assessment
                </Link>
              </header>
              <div className="max-h-80 overflow-y-auto">
                {recent.length ? (
                  <ul className="divide-y divide-steel-100">
                    {recent.map((entry) => (
                      <li key={entry.id} className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-steel-50/60">
                        <Link
                          to={`/components/${entry.component_id}`}
                          className="font-mono text-xs font-semibold text-navy-900 hover:text-accent"
                        >
                          {entry.component_id}
                        </Link>
                        <RecommendationBadge recommendation={entry.recommendation} size="sm" />
                        <span className="text-xs text-steel-500">
                          {formatPercent(entry.confidence, 1)} confidence
                        </span>
                        {entry.safety_flag ? (
                          <span className="badge bg-red-100 text-red-800">Inspection required</span>
                        ) : null}
                        <span className="ml-auto text-[0.65rem] text-steel-400">
                          {formatDateTime(entry.predicted_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="px-5 py-8 text-center text-sm text-steel-400">
                    No assessments recorded yet. Run one from the AI Prediction page.
                  </p>
                )}
              </div>
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}
