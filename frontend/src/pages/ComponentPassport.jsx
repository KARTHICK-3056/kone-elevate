import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  BookMarked,
  Brain,
  FileText,
  Fingerprint,
  Printer,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { usePassport } from '../hooks/useComponents';
import { usePrediction } from '../hooks/usePrediction';
import Loading from '../components/Loading';
import ErrorMessage, { NoticeBanner } from '../components/ErrorMessage';
import QRCodeDisplay from '../components/QRCodeDisplay';
import QRScanner from '../components/QRScanner';
import ServiceTimeline, { PredictionTimeline } from '../components/ServiceTimeline';
import AuditTimeline from '../components/AuditTimeline';
import PredictionCard from '../components/PredictionCard';
import { LifeProjectionCard, MaterialProfileCard } from '../components/LifeProjection';
import { EarlyWarningCard } from '../components/EarlyWarning';
import QualityCertificateCard from '../components/QualityCertificate';
import ScenarioCard from '../components/ScenarioCard';
import HealthBadge, { RecommendationBadge, SafetyChip, StatusBadge } from '../components/HealthBadge';
import { SpecGrid } from '../components/ComponentCard';
import {
  cx,
  formatAge,
  formatCurrency,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  humanise,
  materialWithGrade,
} from '../utils/formatters';
import { GRADE_NOT_DETERMINED } from '../utils/constants';

/**
 * Digital Component Passport.
 *
 * Two modes:
 *  - `/passport`                lookup + scanner (desk use)
 *  - `/passport/:componentId`   standalone record, optimised for a phone that
 *                               has just scanned the QR label on a component.
 */
export default function ComponentPassport({ standalone = false }) {
  const { componentId } = useParams();
  const navigate = useNavigate();
  const { passport, loading, error, refresh } = usePassport(componentId);
  const { prediction, loading: predicting, predictComponent } = usePrediction();

  const [livePrediction, setLivePrediction] = useState(null);

  // ------------------------------------------------------- lookup screen
  if (!componentId) {
    return (
      <div className="mx-auto max-w-3xl space-y-5">
        <header>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">QR Passport</h1>
          <p className="mt-1 text-sm text-steel-500">
            Scan a component label, or look one up by identifier, to open its digital passport.
          </p>
        </header>

        <NoticeBanner tone="blue" icon={ScanLine}>
          Camera access needs a secure context (https or localhost) and user permission. The manual
          lookup below always works, so a denied camera never blocks a technician.
        </NoticeBanner>

        <QRScanner onResolved={(resolvedId) => navigate(`/passport/${resolvedId}`)} />
      </div>
    );
  }

  if (loading) return <Loading label={`Loading passport ${componentId}...`} />;

  if (error) {
    return (
      <div className={standalone ? 'mx-auto max-w-xl p-4' : ''}>
        <ErrorMessage
          error={error}
          onRetry={refresh}
          title={error.status === 404 ? 'Component not found' : 'Passport unavailable'}
        />
        <div className="mt-4 flex gap-2">
          <Link to="/passport" className="btn-secondary">
            Look up another component
          </Link>
          {!standalone ? (
            <Link to="/components" className="btn-ghost">
              Back to components
            </Link>
          ) : null}
        </div>
      </div>
    );
  }

  if (!passport) return null;

  const { component, impact } = passport;
  const standards = passport.standards_basis;
  const dpp = passport.dpp;
  const latest = passport.predictions?.[0];
  const shown = livePrediction || prediction;

  const runAssessment = async () => {
    const result = await predictComponent(component.component_id);
    if (result) {
      setLivePrediction(result);
      refresh();
    }
  };

  const content = (
    <div className="space-y-5">
      {/* --------------------------------------------------- safety gate */}
      {passport.safety_flag ? (
        <div className="safety-banner" role="alert">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-base font-extrabold uppercase tracking-wide">
              {passport.safety_message}
            </p>
            <p className="mt-0.5 text-xs font-normal text-red-700">
              {component.component_type} is a safety-critical component. Any AI recommendation is
              advisory; a qualified engineer must inspect it before the recommendation is acted on.
            </p>
          </div>
        </div>
      ) : null}

      {/* ------------------------------------------------- passport header */}
      <section className="card overflow-hidden">
        <div className="bg-navy-900 px-5 py-5 text-white sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-accent-light">
                Digital Component Passport
              </p>
              <h1 className="mt-1 font-mono text-2xl font-extrabold tracking-tight sm:text-3xl">
                {component.component_id}
              </h1>
              <p className="mt-1 text-sm text-navy-200">
                {component.component_type} - {materialWithGrade(component.material, component.material_grade_label)}
              </p>
              <p className="text-xs text-navy-300">Serial {component.serial_number}</p>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <StatusBadge status={component.current_status} />
                <RecommendationBadge recommendation={latest?.recommendation} />
                <HealthBadge score={component.health_score} />
                {passport.safety_flag ? <SafetyChip /> : null}
                {component.life_cycle_number > 1 ? (
                  <span
                    className="badge bg-emerald-100 text-emerald-800"
                    title="Historical record: a later service life was recorded for this component before complete components stopped being refitted. Kept as history."
                  >
                    Life {component.life_cycle_number}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="rounded-xl bg-white p-3">
              <QRCodeDisplay
                componentId={component.component_id}
                dataUri={passport.qr_data_uri}
                // No passportUrl: the link follows the address this page was
                // opened on (a phone on the LAN, not the server's localhost).
                size={150}
                showActions={false}
              />
            </div>
          </div>
        </div>

        <div className="no-print flex flex-wrap gap-2 border-t border-steel-200 bg-steel-50 px-5 py-3">
          <button type="button" className="btn-accent" onClick={runAssessment} disabled={predicting}>
            <Brain className="h-4 w-4" aria-hidden="true" />
            {predicting ? 'Running assessment...' : 'Run AI Assessment'}
          </button>
          <button type="button" className="btn-secondary" onClick={() => window.print()}>
            <Printer className="h-4 w-4" aria-hidden="true" />
            Print passport
          </button>
          <Link to={`/components/${component.component_id}`} className="btn-secondary">
            <FileText className="h-4 w-4" aria-hidden="true" />
            Full record
          </Link>
          <Link to="/passport" className="btn-ghost">
            <ScanLine className="h-4 w-4" aria-hidden="true" />
            Scan another
          </Link>
        </div>
      </section>

      {/* --------------------------------------------- live AI assessment */}
      {shown ? <PredictionCard prediction={shown} /> : null}

      {/* ------------------------------------------------------- identity */}
      <div className="grid gap-5 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <header className="card-header">
            <h2 className="card-title">Identity and origin</h2>
          </header>
          <div className="card-body">
            <SpecGrid
              items={[
                { label: 'Manufacturer', value: component.manufacturer },
                { label: 'Material', value: component.material },
                {
                  label: 'Material grade',
                  value:
                    component.material_grade_label || passport.material_profile?.grade_label || GRADE_NOT_DETERMINED,
                },
                { label: 'Origin', value: component.origin },
                { label: 'Installation date', value: formatDate(component.installation_date) },
                { label: 'Age', value: formatAge(component.component_age) },
                { label: 'Location', value: component.location },
                { label: 'QR token', value: component.qr_token },
              ]}
            />
          </div>
        </section>

        <section className="card">
          <header className="card-header">
            <h2 className="card-title">Latest assessment</h2>
          </header>
          <div className="card-body space-y-2 text-sm">
            {latest ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-steel-500">Recommendation</span>
                  <RecommendationBadge recommendation={latest.recommendation} size="sm" />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-steel-500">Confidence</span>
                  <span className="font-mono font-semibold">{formatPercent(latest.confidence, 1)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-steel-500">Health score</span>
                  <span className="font-mono font-semibold">{latest.health_score}/100</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-steel-500">Model</span>
                  <span className="font-mono text-xs">{latest.model_version}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-steel-500">Assessed</span>
                  <span className="text-xs">{formatDateTime(latest.predicted_at)}</span>
                </div>
                <p className="pt-2 text-[0.7rem] text-steel-400">{passport.disclaimer}</p>
              </>
            ) : (
              <p className="text-steel-500">
                No AI assessment recorded yet. Run one with the button above.
              </p>
            )}
          </div>
        </section>
      </div>

      {/* ------------------------------------------------ operating history */}
      <section className="card">
        <header className="card-header">
          <h2 className="card-title">Operating and condition data</h2>
        </header>
        <div className="card-body">
          <SpecGrid
            columns={4}
            items={[
              { label: 'Operating hours', value: formatNumber(component.operating_hours), unit: 'h' },
              { label: 'Load cycles', value: formatNumber(component.load_cycles) },
              { label: 'Average load', value: formatNumber(component.average_load), unit: 'kg' },
              { label: 'Vibration', value: component.vibration, unit: 'mm/s' },
              { label: 'Temperature', value: component.temperature, unit: 'C' },
              { label: 'Service visits', value: component.service_count },
              { label: 'Repairs', value: component.repair_count },
              { label: 'Failures', value: component.failure_history },
              { label: 'Inspection score', value: component.inspection_score, unit: '/100' },
              { label: 'Last service', value: formatDate(component.last_service_date) },
              { label: 'Days since service', value: component.days_since_last_service },
              { label: 'Health score', value: component.health_score ?? '-', unit: '/100' },
            ]}
          />
        </div>
      </section>

      {/* ------------------------------ material + usage-adjusted life */}
      <MaterialProfileCard profile={passport.material_profile} />
      <QualityCertificateCard certificate={passport.quality_certificate} />
      <LifeProjectionCard life={passport.life_assessment} />
      <EarlyWarningCard forecast={passport.early_warning} />
      {passport.scenarios?.length ? (
        <ScenarioCard
          componentId={component.component_id}
          scenarios={passport.scenarios}
          allowSimulate={!standalone}
        />
      ) : null}

      {/* --------------------------------------------------------- impact */}
      {impact ? (
        <section className="card">
          <header className="card-header">
            <div>
              <h2 className="card-title">Circular impact of this component</h2>
              <p className="mt-0.5 text-xs text-steel-500">
                Based on the latest AI recommendation and configurable prototype constants.
              </p>
            </div>
            <span className="badge bg-amber-100 text-amber-900">Prototype estimate</span>
          </header>
          <div className="card-body grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-emerald-800">
                Recovery value
              </p>
              <p className="font-mono text-xl font-bold text-emerald-900">
                {formatCurrency(impact.estimated_recovery_value, impact.currency_symbol)}
              </p>
              <p className="text-[0.7rem] text-emerald-800">
                of {formatCurrency(impact.new_part_cost, impact.currency_symbol)} new-part cost
              </p>
            </div>
            <div className="rounded-lg border border-steel-200 bg-steel-50 p-3">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-600">
                Component mass
              </p>
              <p className="font-mono text-xl font-bold text-navy-900">
                {formatNumber(impact.component_mass_kg)} kg
              </p>
              <p className="text-[0.7rem] text-steel-500">
                {humanise(impact.recommendation) || 'Not assessed'} route
              </p>
            </div>
          </div>
        </section>
      ) : null}

      {/* ------------------------------------------- standards + passport id */}
      <div className="grid gap-5 lg:grid-cols-2">
        {standards ? <StandardsBasis standards={standards} /> : null}
        {dpp ? <PassportIdentity dpp={dpp} /> : null}
      </div>

      {/* ------------------------------------------------ lifecycle history */}
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="card">
          <header className="card-header">
            <h2 className="card-title">Service history</h2>
          </header>
          <div className="card-body max-h-[520px] overflow-y-auto">
            <ServiceTimeline events={passport.service_events} />
          </div>
        </section>

        <div className="space-y-5">
          <section className="card">
            <header className="card-header">
              <h2 className="card-title">Decision history</h2>
            </header>
            <div className="card-body max-h-64 overflow-y-auto">
              <PredictionTimeline predictions={passport.predictions} />
            </div>
          </section>

          <section className="card">
            <header className="card-header">
              <div>
                <h2 className="card-title">
                  <ShieldCheck className="mr-1.5 inline h-4 w-4" aria-hidden="true" />
                  Audit trail
                </h2>
                <p className="mt-0.5 text-xs text-steel-500">
                  Tamper-evident SHA-256 chain for this component.
                </p>
              </div>
            </header>
            <div className="card-body max-h-64 overflow-y-auto">
              <AuditTimeline entries={passport.audit_trail} showEntity={false} />
            </div>
          </section>
        </div>
      </div>

      <p className="rounded-lg bg-steel-100 px-4 py-3 text-[0.7rem] text-steel-600">
        <strong className="text-navy-800">Data disclosure. </strong>
        {passport.data_notice} Passport generated {formatDateTime(passport.generated_at)}.
      </p>
    </div>
  );

  if (!standalone) return content;

  // Standalone (post-scan) layout: minimal chrome, mobile-first.
  return (
    <div className="min-h-screen bg-steel-50">
      <div className="mx-auto max-w-4xl px-3 py-4 sm:px-6 sm:py-6">
        <Link to="/" className="no-print btn-ghost btn-sm -ml-2 mb-3">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Open KONE ELEVATE
        </Link>
        {content}
        <footer className="no-print mt-6 border-t border-steel-200 pt-4 text-center">
          <p className="text-[0.65rem] text-steel-400">
            KONE ELEVATE prototype - Team CodeFather, SRM IST Ramapuram. Independent student project,
            not affiliated with KONE Corporation.
          </p>
        </footer>
      </div>
    </div>
  );
}

/**
 * The published standards this component type is assessed against.
 *
 * Clause pointers that have not been checked against the purchased standard
 * are labelled as such, deliberately and visibly. Showing a technician an
 * unverified clause number as though it were authoritative would be worse
 * than showing no clause at all.
 */
export function StandardsBasis({ standards }) {
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Standards basis</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Published standards governing a {standards.component_type}
          </p>
        </div>
        <BookMarked className="h-5 w-5 text-steel-400" aria-hidden="true" />
      </header>
      <ul className="divide-y divide-steel-100">
        {standards.citations.map((citation, index) => (
          <li key={`${citation.standard}-${citation.clause || index}`} className="px-4 py-3">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-mono text-sm font-bold text-navy-900">{citation.standard}</span>
              {citation.clause ? (
                <span className="rounded bg-steel-100 px-1.5 py-0.5 font-mono text-[0.7rem] text-steel-700">
                  Clause {citation.clause}
                </span>
              ) : null}
              {citation.verification === 'CLAUSE_UNVERIFIED' ? (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-amber-800">
                  Clause unverified
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs font-medium text-steel-700">{citation.title}</p>
            {citation.clause_topic ? (
              <p className="mt-0.5 text-xs text-steel-500">{citation.clause_topic}</p>
            ) : null}
            <p className="mt-1.5 text-xs leading-relaxed text-steel-500">{citation.relevance}</p>
          </li>
        ))}
      </ul>
      {standards.unverified_clause_count ? (
        <p className="border-t border-steel-100 bg-amber-50/60 px-4 py-3 text-[0.7rem] leading-relaxed text-amber-900">
          {standards.verification_notice}
        </p>
      ) : null}
    </section>
  );
}

/** Digital Product Passport identity under CPR (EU) 2024/3110. */
export function PassportIdentity({ dpp }) {
  const registered = dpp.registry_status === 'REGISTERED';
  const operator = dpp.economic_operator || {};

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Digital Product Passport</h2>
          <p className="mt-0.5 text-xs text-steel-500">{dpp.regulation}</p>
        </div>
        <Fingerprint className="h-5 w-5 text-steel-400" aria-hidden="true" />
      </header>
      <dl className="divide-y divide-steel-100">
        <div className="px-4 py-2.5">
          <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
            Persistent identifier
          </dt>
          <dd className="mt-0.5 break-all font-mono text-xs text-navy-900">{dpp.dpp_id}</dd>
        </div>
        <div className="px-4 py-2.5">
          <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
            Resolves to
          </dt>
          <dd className="mt-0.5 break-all font-mono text-xs text-steel-600">{dpp.resolver_url}</dd>
        </div>
        <div className="flex items-center justify-between gap-4 px-4 py-2.5">
          <dt className="text-sm text-steel-600">Registry status</dt>
          <dd
            className={cx(
              'rounded px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide',
              registered ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800',
            )}
          >
            {humanise(dpp.registry_status)}
          </dd>
        </div>
        <div className="px-4 py-2.5">
          <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
            Economic operator
          </dt>
          <dd className="mt-0.5 text-xs text-navy-900">{operator.name}</dd>
          {operator.note ? (
            <dd className="mt-1 text-[0.7rem] leading-relaxed text-amber-800">{operator.note}</dd>
          ) : null}
        </div>
      </dl>
      <div className="border-t border-steel-100 px-4 py-3">
        <a
          href={dpp.export_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs font-semibold text-accent hover:underline"
        >
          View the full registry-shaped export
        </a>
      </div>
    </section>
  );
}
