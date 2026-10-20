import { Coins, Info, Recycle } from 'lucide-react';
import { formatCurrency, formatNumber, formatPercentPoints, humanise } from '../utils/formatters';

/**
 * Economic impact panel.
 *
 * Every figure here is derived from configurable constants, so the
 * "Prototype estimate" caption is rendered unconditionally - it is not an
 * optional decoration.
 */
export default function ImpactCard({ impact, title = 'Circular impact', compact = false }) {
  if (!impact) return null;

  const symbol = impact.currency_symbol || 'Rs.';

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h3 className="card-title">{title}</h3>
          <p className="mt-0.5 text-xs text-steel-500">
            Estimated value retained by keeping components and their parts in circulation.
          </p>
        </div>
        <span className="badge bg-amber-100 text-amber-900">
          <Info className="h-3 w-3" aria-hidden="true" />
          Prototype estimate
        </span>
      </header>

      <div className="card-body space-y-4">
        <div className="grid grid-cols-1 gap-3">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-800">
              <Coins className="h-3.5 w-3.5" aria-hidden="true" />
              Recovery value
            </p>
            <p className="mt-1 font-mono text-2xl font-bold text-emerald-900">
              {formatCurrency(
                impact.total_recovery_value ?? impact.estimated_recovery_value,
                symbol,
              )}
            </p>
            {impact.total_new_part_cost ? (
              <p className="mt-1 text-xs text-emerald-800">
                {formatPercentPoints(impact.avoided_procurement_share_percent, 1)} of the{' '}
                {formatCurrency(impact.total_new_part_cost, symbol)} new-part cost
              </p>
            ) : null}
            {impact.new_part_cost ? (
              <p className="mt-1 text-xs text-emerald-800">
                New part costs {formatCurrency(impact.new_part_cost, symbol)}
              </p>
            ) : null}
          </div>

        </div>

        {!compact && impact.components_assessed !== undefined ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-steel-100 p-3">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
                Assessed
              </p>
              <p className="font-mono text-lg font-bold text-navy-900">
                {formatNumber(impact.components_assessed)}
              </p>
            </div>
            <div className="rounded-lg bg-steel-100 p-3">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
                Diverted from disposal
              </p>
              <p className="font-mono text-lg font-bold text-navy-900">
                {formatNumber(impact.components_diverted_from_disposal)}
              </p>
            </div>
            <div className="rounded-lg bg-steel-100 p-3">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
                Diversion rate
              </p>
              <p className="font-mono text-lg font-bold text-navy-900">
                {formatPercentPoints(impact.diversion_rate_percent, 1)}
              </p>
            </div>
          </div>
        ) : null}

        {!compact && impact.by_disposition ? (
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-steel-500">
              <Recycle className="h-3.5 w-3.5" aria-hidden="true" />
              By recommendation
            </p>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Recommendation</th>
                    <th className="text-right">Components</th>
                    <th className="text-right">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(impact.by_disposition).map(([label, values]) => (
                    <tr key={label}>
                      <td className="font-semibold">{humanise(label)}</td>
                      <td className="text-right font-mono">{formatNumber(values.count)}</td>
                      <td className="text-right font-mono">{formatCurrency(values.value, symbol)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        <p className="rounded-lg bg-amber-50 px-3 py-2 text-[0.7rem] text-amber-900">
          {impact.disclaimer}
        </p>
      </div>
    </section>
  );
}

/** Table of the configurable constants behind the estimates. */
export function ImpactAssumptions({ constants }) {
  if (!constants) return null;

  const types = Object.keys(constants.new_part_cost || {});

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h3 className="card-title">Impact model assumptions</h3>
          <p className="mt-0.5 text-xs text-steel-500">
            Illustrative constants from backend configuration. Replace with validated engineering
            data before any external reporting.
          </p>
        </div>
      </header>
      <div className="card-body space-y-4">
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Component type</th>
                <th className="text-right">New part cost</th>
                <th className="text-right">Mass (kg)</th>
              </tr>
            </thead>
            <tbody>
              {types.map((type) => (
                <tr key={type}>
                  <td>{type}</td>
                  <td className="text-right font-mono">
                    {formatCurrency(constants.new_part_cost[type], constants.currency_symbol || 'Rs.', {
                      compact: false,
                    })}
                  </td>
                  <td className="text-right font-mono">
                    {formatNumber(constants.component_mass_kg?.[type])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-steel-500">
              Value recovery factor
            </p>
            <ul className="space-y-0.5 text-sm text-steel-600">
              {Object.entries(constants.value_recovery_factor || {}).map(([label, value]) => (
                <li key={label} className="flex justify-between">
                  <span>{label}</span>
                  <span className="font-mono">{(value * 100).toFixed(0)}%</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
