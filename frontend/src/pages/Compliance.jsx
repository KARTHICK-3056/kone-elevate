import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Download,
  FileCheck2,
  Recycle,
  RefreshCw,
  ScrollText,
  ShieldAlert,
  Sigma,
} from 'lucide-react';
import { useCompliance } from '../hooks/useCompliance';
import { complianceApi } from '../api/client';
import Loading from '../components/Loading';
import ErrorMessage, { NoticeBanner } from '../components/ErrorMessage';
import StatCard from '../components/StatCard';
import {
  CriticalRawMaterialsChart,
  MaterialFlowChart,
  TreatmentRouteChart,
} from '../components/Charts';
import { recommendationStyle } from '../utils/constants';
import { cx, downloadBlob, formatDecimal, formatNumber, humanise, shortHash } from '../utils/formatters';

const TABS = [
  { id: 'esrs', label: 'ESRS E5 (EU)' },
  { id: 'brsr', label: 'BRSR (India)' },
  { id: 'evidence', label: 'Evidence' },
];

/**
 * Regulatory disclosures derived from the material-flow ledger.
 *
 * Deliberately shows its own limits: the estimated-mass share, the unverified
 * standard clauses and the missing external anchor witness are all rendered as
 * prominently as the headline tonnages. A sustainability controller who files
 * one of these numbers without seeing those caveats has been misled by the UI.
 */
export default function Compliance() {
  const {
    period,
    setPeriod,
    options,
    esrs,
    brsr,
    ledger,
    anchors,
    circularity,
    loading,
    error,
    refresh,
  } = useCompliance();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = TABS.some((item) => item.id === searchParams.get('tab')) ? searchParams.get('tab') : 'esrs';
  const setTab = (id) => setSearchParams(id === 'esrs' ? {} : { tab: id }, { replace: true });
  const [downloading, setDownloading] = useState(false);

  if (loading && !esrs) return <Loading label="Compiling disclosures from the ledger..." />;
  if (error && !esrs) return <ErrorMessage error={error} onRetry={refresh} />;
  if (!esrs || !brsr) return null;

  const inflows = esrs['E5-4_resource_inflows'];
  const outflows = esrs['E5-5_resource_outflows'];

  async function handleExport() {
    setDownloading(true);
    try {
      const blob = await complianceApi.exportEsrsCsv(period);
      downloadBlob(blob, `esrs-e5-${period}.csv`);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">Compliance</h1>
          <p className="mt-0.5 text-sm text-steel-500">
            ESRS E5 and BRSR disclosures computed from the material-flow ledger, with the audit
            hash range needed to re-derive them.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="compliance-period">
            Reporting period
          </label>
          <select
            id="compliance-period"
            value={period}
            onChange={(event) => setPeriod(event.target.value)}
            className="input h-9 w-auto py-0 text-sm"
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleExport}
            disabled={downloading}
            className="btn-secondary h-9 gap-2 px-3 text-sm"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {downloading ? 'Preparing...' : 'CSV'}
          </button>
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="btn-secondary h-9 gap-2 px-3 text-sm"
          >
            <RefreshCw className={cx('h-4 w-4', loading && 'animate-spin')} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      <NoticeBanner>{esrs.notice}</NoticeBanner>

      {/* ------------------------------------------------------------ headline */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Resource inflows"
          value={`${formatDecimal(inflows.total_tonnes, 3)} t`}
          hint={`${formatNumber(inflows.total_units)} components entering service`}
          tone="navy"
          icon={Sigma}
          estimate
        />
        <StatCard
          label="Secondary share (ESRS E5-4 term)"
          value={`${formatDecimal(inflows.secondary_reused_share_percent, 1)}%`}
          hint={`${formatDecimal(inflows.secondary_reused_tonnes, 3)} t secondary material, as ESRS E5-4 defines it`}
          tone="continue"
          estimate
        />
        <StatCard
          label="Resource outflows"
          value={`${formatDecimal(outflows.total_tonnes, 3)} t`}
          hint={`${formatNumber(outflows.total_units)} components leaving the fleet`}
          tone="accent"
          estimate
        />
        <StatCard
          label="Diverted from disposal"
          value={`${formatDecimal(outflows.diverted_from_disposal_percent, 1)}%`}
          hint={`${formatDecimal(outflows.directed_to_disposal_tonnes, 3)} t directed to disposal`}
          tone={outflows.directed_to_disposal_percent > 25 ? 'warning' : 'continue'}
          estimate
        />
      </div>

      <EstimateWarning inflows={inflows} outflows={outflows} ledger={ledger} />

      {circularity ? <CircularitySection data={circularity} /> : null}

      {/* ---------------------------------------------------------------- tabs */}
      <div
        className="sticky top-16 z-20 -mx-4 flex gap-1 overflow-x-auto border-b border-steel-200 bg-steel-50/95 px-4 backdrop-blur [scrollbar-width:none] sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
        role="tablist"
        aria-label="Disclosure frameworks"
      >
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cx(
              'shrink-0 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold transition-colors',
              tab === item.id
                ? 'border-accent text-navy-900'
                : 'border-transparent text-steel-500 hover:text-navy-700',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'esrs' ? <EsrsPanel report={esrs} /> : null}
      {tab === 'brsr' ? <BrsrPanel report={brsr} /> : null}
      {tab === 'evidence' ? <EvidencePanel report={esrs} ledger={ledger} anchors={anchors} /> : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/** The caveat that decides whether any of this is fileable. */
function EstimateWarning({ inflows, outflows, ledger }) {
  const share = Math.max(
    inflows.estimated_mass_share_percent || 0,
    outflows.estimated_mass_share_percent || 0,
  );
  if (!share) return null;

  return (
    <div className="card border-l-4 border-l-amber-400 p-4">
      <div className="flex gap-3">
        <ShieldAlert className="h-5 w-5 shrink-0 text-amber-600" aria-hidden="true" />
        <div className="text-sm">
          <p className="font-bold text-navy-900">
            {formatDecimal(share, 1)}% of the mass above is an estimate, not a weighed value
          </p>
          <p className="mt-1 text-steel-600">
            Component mass falls back to a per-type figure from configuration whenever a unit has
            not been weighed
            {ledger
              ? ` (${formatNumber(ledger.rows_on_estimated_mass)} of ${formatNumber(
                  ledger.total_rows,
                )} ledger rows)`
              : ''}
            . Populate each component&apos;s measured mass and this share falls on its own - no
            code change. Until it does, these tables are a draft, not a disclosure.
          </p>
        </div>
      </div>
    </div>
  );
}

function EsrsPanel({ report }) {
  const inflows = report['E5-4_resource_inflows'];
  const outflows = report['E5-5_resource_outflows'];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <MaterialFlowChart inflows={inflows.by_material} outflows={outflows.by_material} />
        <TreatmentRouteChart routes={outflows.by_route} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <CriticalRawMaterialsChart bySubstance={outflows.critical_raw_materials.by_substance} />
        <DisclosureTable
          title="E5-4 Resource inflows"
          subtitle={`${report.period.start} to ${report.period.end}, in tonnes`}
          rows={[
            ['Total resource inflows', `${formatDecimal(inflows.total_tonnes, 3)} t`],
            ['of which secondary / reused (ESRS term)', `${formatDecimal(inflows.secondary_reused_tonnes, 3)} t`],
            ['Secondary share', `${formatDecimal(inflows.secondary_reused_share_percent, 1)}%`],
            ['Virgin material', `${formatDecimal(inflows.virgin_tonnes, 3)} t`],
            [
              'Critical raw materials',
              `${formatDecimal(inflows.critical_raw_materials.total_crm_kg, 2)} kg`,
            ],
          ]}
        />
      </div>

      <DisclosureTable
        title="E5-5 Resource outflows"
        subtitle="Split between diverted from disposal and directed to disposal, as ESRS requires"
        rows={[
          ['Total resource outflows', `${formatDecimal(outflows.total_tonnes, 3)} t`],
          [
            'Diverted from disposal',
            `${formatDecimal(outflows.diverted_from_disposal_tonnes, 3)} t (${formatDecimal(
              outflows.diverted_from_disposal_percent,
              1,
            )}%)`,
          ],
          [
            'Directed to disposal',
            `${formatDecimal(outflows.directed_to_disposal_tonnes, 3)} t (${formatDecimal(
              outflows.directed_to_disposal_percent,
              1,
            )}%)`,
          ],
          [
            'Critical raw materials',
            `${formatDecimal(outflows.critical_raw_materials.total_crm_kg, 2)} kg`,
          ],
        ]}
      />

      <p className="text-xs leading-relaxed text-steel-500">
        <strong className="text-steel-600">Boundary.</strong> {report.boundary}
      </p>
    </div>
  );
}

function BrsrPanel({ report }) {
  const p2 = report.principle_2_sustainable_safe_goods;
  const p6 = report.principle_6_environment;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <DisclosureTable
          title="Principle 2 - Sustainable and safe goods"
          subtitle={p2.disclosure}
          rows={[
            ['Total inputs', `${formatDecimal(p2.total_input_tonnes, 3)} t`],
            ['Reclaimed inputs', `${formatDecimal(p2.reclaimed_input_tonnes, 3)} t`],
            ['Reclaimed share', `${formatDecimal(p2.reclaimed_input_share_percent, 1)}%`],
          ]}
        />
        <DisclosureTable
          title="Principle 6 - Environment"
          subtitle={p6.disclosure}
          rows={[
            ['Total waste generated', `${formatDecimal(p6.total_waste_tonnes, 3)} t`],
            ['Re-used (BRSR term)', `${formatDecimal(p6.reused_tonnes, 3)} t`],
            ['Recycled (BRSR term)', `${formatDecimal(p6.recycled_tonnes, 3)} t`],
            ['Other recovery', `${formatDecimal(p6.other_recovery_tonnes, 3)} t`],
            ['Total recovered', `${formatDecimal(p6.total_recovered_tonnes, 3)} t`],
            ['Recovered share', `${formatDecimal(p6.recovered_share_percent, 1)}%`],
            ['Directed to disposal', `${formatDecimal(p6.disposed_tonnes, 3)} t`],
          ]}
        />
      </div>
      <p className="text-xs text-steel-500">
        Entity scope: {report.entity_scope}. Framework: {report.framework}.
      </p>
    </div>
  );
}

/** Provenance: what an assurance provider needs to re-derive the numbers. */
function EvidencePanel({ report, ledger, anchors }) {
  const derivation = report.derivation;
  const protectedChain = Boolean(anchors?.externally_witnessed_anchors);

  return (
    <div className="space-y-4">
      <section className="card">
        <header className="card-header">
          <div>
            <h3 className="card-title">Derivation</h3>
            <p className="mt-0.5 text-xs text-steel-500">
              The audit-chain range these figures were computed from
            </p>
          </div>
          <FileCheck2 className="h-5 w-5 text-steel-400" aria-hidden="true" />
        </header>
        <dl className="divide-y divide-steel-100">
          <EvidenceRow label="Ledger rows" value={formatNumber(derivation.ledger_rows)} />
          <EvidenceRow label="Audit entries" value={formatNumber(derivation.audit_entries)} />
          <EvidenceRow label="First hash" value={shortHash(derivation.first_audit_hash) || '-'} mono />
          <EvidenceRow label="Last hash" value={shortHash(derivation.last_audit_hash) || '-'} mono />
          <EvidenceRow
            label="Chain head at generation"
            value={shortHash(derivation.chain_head_hash_at_generation) || '-'}
            mono
          />
        </dl>
        <p className="border-t border-steel-100 px-4 py-3 text-xs leading-relaxed text-steel-500">
          {derivation.verification}
        </p>
      </section>

      <section
        className={cx(
          'card border-l-4 p-4',
          protectedChain ? 'border-l-emerald-400' : 'border-l-red-400',
        )}
      >
        <div className="flex gap-3">
          <ShieldAlert
            className={cx('h-5 w-5 shrink-0', protectedChain ? 'text-emerald-600' : 'text-red-600')}
            aria-hidden="true"
          />
          <div className="text-sm">
            <p className="font-bold text-navy-900">Tamper evidence beyond the database</p>
            <p className="mt-1 text-steel-600">{anchors?.protection}</p>
            {anchors ? (
              <p className="mt-2 text-xs text-steel-500">
                {formatNumber(anchors.total_anchors)} anchor
                {anchors.total_anchors === 1 ? '' : 's'} recorded,{' '}
                {formatNumber(anchors.externally_witnessed_anchors)} with an external witness.
              </p>
            ) : null}
          </div>
        </div>
      </section>

      {ledger ? (
        <section className="card">
          <header className="card-header">
            <div>
              <h3 className="card-title">Material-flow ledger</h3>
              <p className="mt-0.5 text-xs text-steel-500">
                The kilogram record every disclosure is computed from
              </p>
            </div>
            <ScrollText className="h-5 w-5 text-steel-400" aria-hidden="true" />
          </header>
          <dl className="divide-y divide-steel-100">
            <EvidenceRow label="Total rows" value={formatNumber(ledger.total_rows)} />
            {Object.entries(ledger.by_direction || {}).map(([direction, values]) => (
              <EvidenceRow
                key={direction}
                label={direction}
                value={`${formatNumber(values.rows)} rows · ${formatDecimal(values.tonnes, 3)} t`}
              />
            ))}
            <EvidenceRow
              label="Rows on estimated mass"
              value={`${formatNumber(ledger.rows_on_estimated_mass)} (${formatDecimal(
                ledger.estimated_mass_row_share_percent,
                1,
              )}%)`}
            />
            <EvidenceRow
              label="Coverage"
              value={`${ledger.first_flow_date || '-'} to ${ledger.last_flow_date || '-'}`}
            />
          </dl>
        </section>
      ) : null}
    </div>
  );
}

function EvidenceRow({ label, value, mono = false }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-2.5">
      <dt className="text-sm text-steel-600">{label}</dt>
      <dd className={cx('text-sm font-semibold text-navy-900', mono && 'font-mono text-xs')}>
        {value}
      </dd>
    </div>
  );
}

function DisclosureTable({ title, subtitle, rows }) {
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h3 className="card-title">{title}</h3>
          {subtitle ? <p className="mt-0.5 text-xs text-steel-500">{subtitle}</p> : null}
        </div>
      </header>
      <dl className="divide-y divide-steel-100">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-4 px-4 py-2.5">
            <dt className="text-sm text-steel-600">{label}</dt>
            <dd className="text-sm font-bold text-navy-900">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/**
 * Material Circularity Indicator, with the three strategies separated.
 *
 * Kept distinct from the ESRS tiles above on purpose: E5 reports tonnes,
 * this reports circularity, and conflating them is exactly the mistake this
 * section exists to correct - a fleet can improve its carbon and rupee
 * numbers while becoming less circular.
 */
function CircularitySection({ data }) {
  const { strategies, basis_split: basis } = data;
  const percent = Math.round(data.mci_mass_weighted * 100);

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">
            <Recycle className="mr-1.5 inline h-4 w-4 text-accent" aria-hidden="true" />
            Material Circularity Indicator
          </h2>
          <p className="mt-0.5 text-xs text-steel-500">
            0 = fully linear (virgin in, landfill out), 1 = fully circular. Mass-weighted across{' '}
            {formatNumber(data.components_scored)} components, from the same ledger the E5 report
            uses.
          </p>
        </div>
        <span className="badge bg-amber-100 text-amber-900">Prototype estimate</span>
      </header>

      <div className="card-body space-y-4">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
          <div>
            <p className="font-mono text-4xl font-extrabold text-navy-900">
              {data.mci_mass_weighted.toFixed(2)}
            </p>
            <p className="text-[0.7rem] text-steel-500">
              {percent}% circular &middot; unweighted mean {data.mci_unweighted_mean.toFixed(2)}
            </p>
          </div>
          <div className="text-[0.7rem] text-steel-500">
            <p>
              <strong className="text-navy-800">{formatNumber(basis.actual)}</strong> measured from a
              recorded outflow route
            </p>
            <p>
              <strong className="text-navy-800">{formatNumber(basis.projected)}</strong> projected
              from the current AI recommendation
            </p>
          </div>
        </div>

        <div className="h-2 w-full overflow-hidden rounded-full bg-steel-200">
          <div
            className="h-full rounded-full bg-emerald-500"
            style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <StrategyCard
            name="Narrow"
            subtitle="Use less material"
            measured={strategies.narrow.measured}
            note={strategies.narrow.note}
          />
          <StrategyCard
            name="Slow"
            subtitle="Extend service life"
            measured={strategies.slow.measured}
            metrics={[
              [
                'On a 2nd+ life',
                `${formatNumber(strategies.slow.components_on_second_or_later_life)} (${
                  strategies.slow.second_life_share_percent
                }%)`,
              ],
              ['Life achieved vs design', `${strategies.slow.mean_life_achieved_vs_design_percent}%`],
            ]}
          />
          <StrategyCard
            name="Close"
            subtitle="Cycle material back"
            measured={strategies.close.measured}
            metrics={[
              ['Diverted from disposal', `${strategies.close.diverted_from_disposal_percent}%`],
              ['Secondary inflow share', `${strategies.close.secondary_inflow_share_percent}%`],
            ]}
          />
        </div>

        <RLadderBars distribution={data.r_ladder_distribution} />

        <p className="text-[0.7rem] text-steel-400">{data.disclaimer}</p>
      </div>
    </section>
  );
}

/**
 * Where the fleet sits on the value-retention hierarchy, tightest loop
 * first. Each rung is one of the four categories: R4 Continue Using, R7
 * Component Recovery, R8 Material Recovery, R9 Dispose. The rungs that would
 * move, restore or supply a complete component elsewhere are not offered.
 */
const RUNG_CATEGORY = {
  R4: 'CONTINUE_USING',
  R7: 'COMPONENT_RECOVERY',
  R8: 'MATERIAL_RECOVERY',
  R9: 'DISPOSE',
};

function RLadderBars({ distribution }) {
  if (!distribution?.by_rung?.length) return null;
  const peak = Math.max(...distribution.by_rung.map((row) => row.components));

  return (
    <div className="rounded-lg border border-steel-200 p-3">
      <p className="mb-1 text-xs font-bold uppercase tracking-wide text-steel-500">
        Value-retention ladder
      </p>
      <p className="mb-3 text-[0.7rem] text-steel-500">
        Tightest loop first. Each rung is one recommendation category; transferring, restoring or
        rebuilding a complete component for use elsewhere is not offered.
      </p>
      <ul className="space-y-1.5">
        {distribution.by_rung.map((row) => (
          <li key={row.rung} className="flex items-center gap-2">
            <span className="w-7 shrink-0 font-mono text-[0.7rem] font-semibold text-accent">
              {row.rung}
            </span>
            <span className="w-40 shrink-0 truncate text-xs text-navy-800" title={row.name}>
              {humanise(RUNG_CATEGORY[row.rung]) || row.name}
            </span>
            <span className="h-3 min-w-0 flex-1 overflow-hidden rounded-sm bg-steel-100">
              <span
                className="block h-full rounded-sm"
                style={{
                  width: `${peak ? (row.components / peak) * 100 : 0}%`,
                  backgroundColor: recommendationStyle(RUNG_CATEGORY[row.rung])?.hex || '#6a89bd',
                }}
              />
            </span>
            <span className="w-16 shrink-0 text-right font-mono text-xs text-navy-900">
              {row.components} ({row.share_percent}%)
            </span>
          </li>
        ))}
      </ul>
      {distribution.unplaced ? (
        <p className="mt-2 text-[0.7rem] text-steel-400">
          {formatNumber(distribution.unplaced)} not placed - {distribution.unplaced_note}
        </p>
      ) : null}
    </div>
  );
}

function StrategyCard({ name, subtitle, measured, metrics = [], note }) {
  return (
    <div
      className={cx(
        'rounded-lg border p-3',
        measured ? 'border-steel-200 bg-white' : 'border-dashed border-steel-300 bg-steel-50',
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-bold text-navy-900">{name}</p>
        {measured ? null : (
          <span className="badge bg-steel-200 text-steel-700">Not measured</span>
        )}
      </div>
      <p className="mb-2 text-[0.7rem] uppercase tracking-wide text-steel-400">{subtitle}</p>
      {measured ? (
        <dl className="space-y-1">
          {metrics.map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-2">
              <dt className="text-[0.7rem] text-steel-500">{label}</dt>
              <dd className="font-mono text-sm font-semibold text-navy-900">{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-[0.7rem] leading-snug text-steel-500">{note}</p>
      )}
    </div>
  );
}
