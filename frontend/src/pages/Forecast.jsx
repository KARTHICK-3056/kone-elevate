import { AlertTriangle, CalendarClock, MapPin, RefreshCw } from 'lucide-react';
import { useForecast } from '../hooks/useForecast';
import Loading from '../components/Loading';
import ErrorMessage from '../components/ErrorMessage';
import StatCard from '../components/StatCard';
import { CapacityUtilisationChart, ForecastRemovalsChart } from '../components/Charts';
import { formatCurrency, formatNumber } from '../utils/formatters';

const HORIZONS = [12, 24, 36];
const GROUPINGS = [
  { value: 'type', label: 'Component type' },
  { value: 'site', label: 'Site' },
  { value: 'region', label: 'Region' },
];

/** Forecast end-of-life removals and plan component-recovery capacity ahead. */
export default function Forecast() {
  const {
    eol,
    capacity,
    siteImpact,
    model,
    horizon,
    setHorizon,
    groupBy,
    setGroupBy,
    loading,
    error,
    refresh,
  } = useForecast();

  if (loading && !eol) return <Loading label="Forecasting fleet end-of-life..." />;
  if (error && !eol) return <ErrorMessage error={error} onRetry={refresh} />;

  if (model && !model.forecast_available) {
    return (
      <div className="space-y-5">
        <Header horizon={horizon} setHorizon={setHorizon} groupBy={groupBy} setGroupBy={setGroupBy} refresh={refresh} loading={loading} />
        <div className="card p-8 text-center">
          <CalendarClock className="mx-auto h-10 w-10 text-steel-300" aria-hidden="true" />
          <h2 className="mt-3 text-lg font-bold text-navy-900">No forecast model trained yet</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-steel-500">
            The end-of-life forecaster has not been built in this environment. Run{' '}
            <code className="rounded bg-steel-100 px-1.5 py-0.5 font-mono text-xs">
              python scripts/train_forecast.py
            </code>{' '}
            in the backend, then reload this page.
          </p>
        </div>
      </div>
    );
  }

  if (!eol || !capacity) return null;

  const backlog = eol.current_backlog || {};
  const breached = capacity.quarters_over_capacity || [];

  return (
    <div className="space-y-5">
      <Header horizon={horizon} setHorizon={setHorizon} groupBy={groupBy} setGroupBy={setGroupBy} refresh={refresh} loading={loading} />

      {/* ---------------------------------------------------------- headline */}
      <div id="fc-kpis" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard
          label={`Forecast removals (${horizon}m)`}
          value={formatNumber(Math.round(eol.total_expected_removals))}
          hint={`Across ${formatNumber(eol.components_in_scope)} at-risk components`}
          tone="accent"
          estimate
        />
        <StatCard
          label="Current backlog"
          value={formatNumber(backlog.components || 0)}
          hint={`${formatNumber(backlog.recovery_hours_required || 0)} h already past threshold`}
          tone="warning"
        />
        <StatCard
          label="Peak utilisation"
          value={`${capacity.peak_utilisation_percent}%`}
          hint={`Capacity ${formatNumber(capacity.capacity_hours_per_quarter)} h/quarter`}
          tone={breached.length ? 'dispose' : 'continue'}
          estimate
        />
        <StatCard
          label="Bottleneck type"
          value={capacity.bottleneck_component_type || '--'}
          hint="Largest share of forecast workshop hours"
          tone="navy"
        />
      </div>

      {breached.length ? (
        <div className="flex gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
          <div>
            <p className="font-semibold">
              Forecast intake exceeds workshop capacity in {breached.length}{' '}
              {breached.length === 1 ? 'quarter' : 'quarters'}: {breached.join(', ')}.
            </p>
            <p className="mt-0.5 text-xs text-red-800">
              The intake schedule below carries the excess forward rather than dropping it, so the
              deferred hours accumulate visibly.
            </p>
          </div>
        </div>
      ) : null}

      {/* ------------------------------------------------------------ charts */}
      <div id="fc-charts" className="grid scroll-mt-32 grid-cols-1 gap-4 2xl:grid-cols-2">
        <ForecastRemovalsChart groups={eol.groups} quarters={eol.quarters} />
        <CapacityUtilisationChart quarters={capacity.quarters} />
      </div>

      {/* -------------------------------------------------- intake schedule */}
      <section id="fc-schedule" className="card scroll-mt-32">
        <header className="card-header">
          <div>
            <h2 className="card-title">
              <CalendarClock className="mr-1.5 inline h-4 w-4 text-accent" aria-hidden="true" />
              Recommended intake schedule
            </h2>
            <p className="mt-0.5 text-xs text-steel-500">
              Work that cannot be absorbed in the quarter it arrives is carried into the next one.
              Opening backlog is queued ahead of the first quarter&apos;s arrivals.
            </p>
          </div>
        </header>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Quarter</th>
                <th className="text-right">Arriving (h)</th>
                <th className="text-right">Deferred in (h)</th>
                <th className="text-right">Scheduled (h)</th>
                <th className="text-right">Deferred out (h)</th>
              </tr>
            </thead>
            <tbody>
              {capacity.recommended_intake_schedule.map((row) => (
                <tr key={row.quarter}>
                  <td className="font-mono text-xs font-semibold text-navy-900">{row.quarter}</td>
                  <td className="text-right font-mono text-sm">{formatNumber(row.arriving_hours)}</td>
                  <td className="text-right font-mono text-sm text-steel-500">
                    {formatNumber(row.deferred_in_hours)}
                  </td>
                  <td className="text-right font-mono text-sm">{formatNumber(row.scheduled_hours)}</td>
                  <td
                    className={
                      row.deferred_out_hours > 0
                        ? 'text-right font-mono text-sm font-semibold text-red-700'
                        : 'text-right font-mono text-sm text-steel-400'
                    }
                  >
                    {formatNumber(row.deferred_out_hours)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* --------------------------------------------------- site impact */}
      {siteImpact?.sites?.length ? (
        <section id="fc-sites" className="card scroll-mt-32">
          <header className="card-header">
            <div>
              <h2 className="card-title">
                <MapPin className="mr-1.5 inline h-4 w-4 text-accent" aria-hidden="true" />
                Projected quarterly value by site
              </h2>
              <p className="mt-0.5 text-xs text-steel-500">
                {siteImpact.method} All figures are prototype estimates - see the model card and
                impact disclaimers.
              </p>
            </div>
          </header>
          {siteImpact.fleet_average ? (
            <div className="grid grid-cols-1 gap-4 border-b border-steel-100 p-4 sm:grid-cols-2">
              <StatCard
                label="Avg. projected value / site / quarter"
                value={formatCurrency(
                  siteImpact.fleet_average.avg_projected_value_per_site,
                  siteImpact.currency_symbol
                )}
                hint={`Mean across ${siteImpact.fleet_average.sites} site(s)`}
                tone="accent"
                estimate
              />
            </div>
          ) : null}
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Site</th>
                  <th className="text-right">Backlog + forecast (N)</th>
                  <th className="text-right">Projected value</th>
                  <th>Mix source</th>
                </tr>
              </thead>
              <tbody>
                {siteImpact.sites.map((row) => (
                  <tr key={row.site}>
                    <td className="text-sm">{row.site}</td>
                    <td className="text-right font-mono text-sm">
                      {formatNumber(row.projected_components_this_period)}
                    </td>
                    <td className="text-right font-mono text-sm">
                      {formatCurrency(row.projected_value, siteImpact.currency_symbol)}
                    </td>
                    <td>
                      <span
                        className={
                          row.mix_source.startsWith('this site')
                            ? 'badge bg-emerald-100 text-emerald-800'
                            : 'badge bg-amber-100 text-amber-900'
                        }
                      >
                        {row.mix_source.startsWith('this site') ? "Site's own history" : 'Fleet fallback'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {/* ------------------------------------------------------ assumptions */}
      <section id="fc-assumptions" className="card scroll-mt-32 p-5 text-xs text-steel-600">
        <h3 className="mb-2 text-sm font-bold text-navy-900">Model and assumptions</h3>
        <div className="grid gap-2 sm:grid-cols-2">
          <p>
            <strong className="text-navy-800">Model.</strong> {model?.model} {model?.model_version},
            Weibull shape k = {model?.shape_k} (k &gt; 1 means hazard rises with age). Backtest MAPE{' '}
            {model?.mape_overall}% across horizons.
          </p>
          <p>
            <strong className="text-navy-800">Capacity.</strong>{' '}
            {formatNumber(capacity.capacity_hours_per_quarter)} labour hours per quarter;{' '}
            {Math.round(capacity.recovery_routing_rate * 100)}% of removals routed to component
            recovery (sub-component dismantling and testing).
          </p>
        </div>
        <p className="mt-2">{capacity.assumptions?.note}</p>
        <p className="mt-1">{backlog.note}</p>
      </section>
    </div>
  );
}

function Header({ horizon, setHorizon, groupBy, setGroupBy, refresh, loading }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">Forecast</h1>
        <p className="mt-1 text-sm text-steel-500">
          End-of-life projection and component-recovery capacity planning.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="select w-auto"
          value={groupBy}
          onChange={(event) => setGroupBy(event.target.value)}
          aria-label="Group forecast by"
        >
          {GROUPINGS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          className="select w-auto"
          value={horizon}
          onChange={(event) => setHorizon(Number(event.target.value))}
          aria-label="Forecast horizon"
        >
          {HORIZONS.map((months) => (
            <option key={months} value={months}>
              {months} months
            </option>
          ))}
        </select>
        <button type="button" className="btn-secondary" onClick={refresh} disabled={loading}>
          <RefreshCw className={loading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
          Refresh
        </button>
      </div>
    </header>
  );
}
