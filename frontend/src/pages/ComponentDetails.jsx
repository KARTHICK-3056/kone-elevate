import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  Activity,
  ArrowLeft,
  Brain,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  FlaskConical,
  Layers,
  Printer,
  QrCode,
  Radio,
  ShieldCheck,
  Trash2,
  Wrench,
} from 'lucide-react';
import { auditApi, componentsApi, simulationApi } from '../api/client';
import { useComponent, useLifeAssessment, usePassport } from '../hooks/useComponents';
import { LifeProjectionCard, MaterialProfileCard } from '../components/LifeProjection';
import { EarlyWarningCard } from '../components/EarlyWarning';
import InspectionForm from '../components/InspectionForm';
import FieldDataCard from '../components/FieldDataCard';
import ScenarioCard from '../components/ScenarioCard';
import QRCodeDisplay from '../components/QRCodeDisplay';
import QualityCertificateCard from '../components/QualityCertificate';
import { PassportIdentity, StandardsBasis } from './ComponentPassport';

/** Types with a measurement checklist and the simulation's load physics. */
/** Types the Simulation page can run (the four drivetrain components). */
const FIELD_TYPES = ['Motor', 'Steel Rope', 'Sheave', 'Brake'];
/** Types with a measured inspection checklist. */
const INSPECTION_TYPES = [...FIELD_TYPES, 'Governor'];
import { usePrediction } from '../hooks/usePrediction';
import Loading from '../components/Loading';
import ErrorMessage from '../components/ErrorMessage';
import Modal, { ConfirmModal } from '../components/Modal';
import PredictionCard from '../components/PredictionCard';
import ServiceTimeline, { PredictionTimeline } from '../components/ServiceTimeline';
import AuditTimeline from '../components/AuditTimeline';
import ImpactCard from '../components/ImpactCard';
import HealthBadge, { RecommendationBadge, SafetyChip, StatusBadge } from '../components/HealthBadge';
import { SpecGrid } from '../components/ComponentCard';
import ServiceEventForm from './partials/ServiceEventForm';
import { GRADE_NOT_DETERMINED, LIFECYCLE_STATUSES } from '../utils/constants';
import { cx, formatAge, formatDate, formatNumber, formatPercent, humanise, materialWithGrade } from '../utils/formatters';

const ALL_TABS = [
  { id: 'overview', label: 'Overview', icon: ClipboardList },
  { id: 'passport', label: 'Passport & QR', icon: QrCode },
  { id: 'material', label: 'Material', icon: Layers },
  { id: 'life', label: 'Life & forecast', icon: Activity },
  { id: 'sensors', label: 'Sensor data', icon: Radio },
  { id: 'scenarios', label: 'Scenarios', icon: FlaskConical, types: FIELD_TYPES },
  { id: 'service', label: 'Service history', icon: Wrench },
  { id: 'assessments', label: 'AI assessments', icon: Brain },
  { id: 'audit', label: 'Audit trail', icon: ShieldCheck },
];

const tabsFor = (componentType) => ALL_TABS.filter((item) => !item.types || item.types.includes(componentType));

/** A compact summary that opens the tab holding the full detail. */
function GlanceTile({ label, value, detail, onOpen, tone = 'text-navy-900' }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex min-w-0 flex-col rounded-xl border border-steel-200 bg-white p-4 text-left shadow-card transition hover:border-accent/50 hover:shadow-elevated"
    >
      <span className="flex items-center justify-between gap-2 text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
        {label}
        <ChevronRight className="h-3.5 w-3.5 text-steel-400 transition group-hover:translate-x-0.5 group-hover:text-accent" aria-hidden="true" />
      </span>
      <span className={cx('mt-1 truncate font-mono text-lg font-bold', tone)}>{value}</span>
      {detail ? <span className="mt-0.5 line-clamp-2 text-xs text-steel-500">{detail}</span> : null}
    </button>
  );
}

/** Full working view of one component: specs, history, assessment, actions. */
export default function ComponentDetails() {
  const { componentId } = useParams();
  const { component, events, predictions, loading, error, refresh } = useComponent(componentId);
  const { life, refresh: refreshLife } = useLifeAssessment(componentId);
  const { passport } = usePassport(componentId);
  const {
    prediction,
    loading: predicting,
    error: predictionError,
    predictComponent,
  } = usePrediction();

  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'overview';
  const setTab = (id) => {
    setSearchParams(id === 'overview' ? {} : { tab: id }, { replace: true });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const [showEventForm, setShowEventForm] = useState(false);
  const [showInspection, setShowInspection] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [auditEntries, setAuditEntries] = useState([]);
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Loaded whenever the audit tab is shown, so a shared ?tab=audit link works too.
  useEffect(() => {
    if (tab !== 'audit') return undefined;
    let cancelled = false;
    auditApi
      .forEntity('component', componentId)
      .then((entries) => !cancelled && setAuditEntries(entries))
      .catch((err) => !cancelled && setActionError(err));
    return () => {
      cancelled = true;
    };
  }, [tab, componentId]);

  const runAssessment = async () => {
    setActionError(null);
    const result = await predictComponent(componentId);
    if (result) {
      setTab('overview');
      refresh();
      refreshLife();
    }
  };

  const changeStatus = async (status) => {
    setBusy(true);
    setActionError(null);
    try {
      await componentsApi.update(componentId, { current_status: status });
      refresh();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  };

  const removeComponent = async () => {
    setBusy(true);
    try {
      await componentsApi.remove(componentId);
      window.location.assign('/components');
    } catch (err) {
      setActionError(err);
      setBusy(false);
      setShowDelete(false);
    }
  };

  if (loading) return <Loading label={`Loading ${componentId}...`} />;
  if (error) return <ErrorMessage error={error} onRetry={refresh} title="Component unavailable" />;
  if (!component) return null;

  const latest = component.latest_prediction;
  const shownPrediction = prediction;
  const tabs = tabsFor(component.component_type);
  const assessment = life?.life_assessment;
  const profile = life?.material_profile;
  const forecast = life?.early_warning;

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------------------ head */}
      <div>
        <Link to="/components" className="btn-ghost btn-sm -ml-2 mb-2">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to components
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-mono text-2xl font-extrabold tracking-tight text-navy-900">
              {component.component_id}
            </h1>
            <p className="mt-1 text-sm text-steel-500">
              {component.component_type} - {materialWithGrade(component.material, component.material_grade_label)} -{' '}
              {component.serial_number}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge status={component.current_status} />
              <RecommendationBadge recommendation={latest?.recommendation} />
              <HealthBadge score={component.health_score} />
              {component.is_safety_critical ? <SafetyChip /> : null}
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

          <div className="grid w-full grid-cols-2 gap-2 max-sm:[&>*]:px-2 max-sm:[&>*]:py-2.5 max-sm:[&>*]:text-xs sm:flex sm:w-auto sm:flex-wrap sm:justify-end">
            <button
              type="button"
              className={cx('btn-secondary', tab === 'passport' && 'ring-2 ring-accent')}
              onClick={() => setTab('passport')}
              title="View digital passport and QR code"
            >
              <QrCode className="h-4 w-4" aria-hidden="true" />
              Passport & QR
            </button>
            <button type="button" className="btn-secondary" onClick={() => setShowEventForm(true)}>
              <Wrench className="h-4 w-4" aria-hidden="true" />
              Add service event
            </button>
            {INSPECTION_TYPES.includes(component.component_type) ? (
              <button type="button" className="btn-secondary" onClick={() => setShowInspection(true)}>
                <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
                Record inspection
              </button>
            ) : null}
            {FIELD_TYPES.includes(component.component_type) ? (
              <>
                <Link
                  to={`/simulation?component=${encodeURIComponent(component.component_id)}`}
                  className="btn-secondary"
                >
                  <FlaskConical className="h-4 w-4" aria-hidden="true" />
                  Simulate
                </Link>
              </>
            ) : null}
            <button
              type="button"
              className="btn-accent col-span-2 -order-1 max-sm:!text-sm sm:order-none"
              onClick={runAssessment}
              disabled={predicting}
            >
              <Brain className="h-4 w-4" aria-hidden="true" />
              {predicting ? 'Assessing...' : 'Run AI assessment'}
            </button>
          </div>
        </div>
      </div>

      {/* `predictComponent` swallows its failure into the hook's own error
          state and returns null, so a refused assessment (a read-only
          auditor, say) would otherwise look like nothing happened at all. */}
      {actionError || predictionError ? (
        <ErrorMessage error={actionError || predictionError} compact />
      ) : null}

      {/* ---------------------------------------------------------- tabs */}
      <div className="sticky top-16 z-20 -mx-4 border-b border-steel-200 bg-steel-50/95 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <div className="flex gap-1 overflow-x-auto [scrollbar-width:none]" role="tablist" aria-label="Component sections">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
              className={cx(
                'flex shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 py-3 text-sm font-semibold transition-colors sm:px-4',
                tab === item.id
                  ? 'border-accent text-navy-900'
                  : 'border-transparent text-steel-500 hover:text-navy-800',
              )}
            >
              <item.icon className="h-4 w-4" aria-hidden="true" />
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* ------------------------------------------------------- overview */}
      {tab === 'overview' ? (
        <div className="space-y-5">
          {shownPrediction ? <PredictionCard prediction={shownPrediction} /> : null}

          {profile || assessment?.available || forecast?.supported ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {profile ? (
                <GlanceTile
                  label="Material grade"
                  value={profile.designation || profile.primary_material}
                  detail={profile.grading_system || profile.grade_label}
                  onOpen={() => setTab('material')}
                />
              ) : null}
              {assessment?.available ? (
                <GlanceTile
                  label="Life used"
                  value={formatPercent(assessment.life_consumed?.governing, 0)}
                  detail={assessment.status?.message}
                  onOpen={() => setTab('life')}
                  tone={
                    assessment.band === 'red'
                      ? 'text-red-700'
                      : assessment.band === 'amber'
                        ? 'text-amber-700'
                        : 'text-emerald-700'
                  }
                />
              ) : null}
              {assessment?.available ? (
                <GlanceTile
                  label="Projected total life"
                  value={`${Number(assessment.projection?.projected_total_life_years).toFixed(1)} yr`}
                  detail={`Expected ${Number(assessment.design_life_years).toFixed(1)} yr for this type and grade`}
                  onOpen={() => setTab('life')}
                />
              ) : null}
              {forecast?.supported ? (
                <GlanceTile
                  label="Issue forecast"
                  value={forecast.issues?.length ? `${forecast.issues.length} predicted` : 'None predicted'}
                  detail={forecast.headline}
                  onOpen={() => setTab('life')}
                  tone={forecast.issues?.length ? 'text-amber-700' : 'text-emerald-700'}
                />
              ) : null}
            </div>
          ) : null}

          <div className="grid gap-5 lg:grid-cols-3">
            <section className="card lg:col-span-2">
              <header className="card-header">
                <h2 className="card-title">Component record</h2>
              </header>
              <div className="card-body space-y-5">
                <SpecGrid
                  items={[
                    { label: 'Component ID', value: component.component_id },
                    { label: 'Serial number', value: component.serial_number },
                    { label: 'Type', value: component.component_type },
                    { label: 'Material', value: component.material },
                    { label: 'Material grade', value: component.material_grade_label || GRADE_NOT_DETERMINED },
                    { label: 'Manufacturer', value: component.manufacturer },
                    { label: 'Origin', value: component.origin },
                    { label: 'Location', value: component.location },
                    { label: 'Installation date', value: formatDate(component.installation_date) },
                    { label: 'Age', value: formatAge(component.component_age) },
                    { label: 'Lifecycle status', value: humanise(component.current_status) },
                  ]}
                />

                <div>
                  <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-steel-500">
                    Operating history
                  </h3>
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
                    ]}
                  />
                </div>

                {component.notes ? (
                  <div className="rounded-lg bg-steel-100 p-3 text-sm text-steel-700">
                    <span className="font-semibold text-navy-800">Notes: </span>
                    {component.notes}
                  </div>
                ) : null}
              </div>
            </section>

            <div className="space-y-5">
              <section className="card">
                <header className="card-header">
                  <h2 className="card-title">Lifecycle actions</h2>
                </header>
                <div className="card-body space-y-3">
                  <div>
                    <label className="label" htmlFor="status-select">
                      Update lifecycle status
                    </label>
                    <select
                      id="status-select"
                      className="select"
                      value={component.current_status}
                      onChange={(event) => changeStatus(event.target.value)}
                      disabled={busy}
                    >
                      {LIFECYCLE_STATUSES.map((status) => (
                        <option key={status} value={status}>
                          {humanise(status)}
                        </option>
                      ))}
                    </select>
                    <p className="mt-1 text-[0.7rem] text-steel-400">
                      Lifecycle status is a human decision and is deliberately separate from the AI
                      recommendation.
                    </p>
                  </div>

                  <button
                    type="button"
                    className="btn-ghost w-full text-dispose hover:bg-red-50"
                    onClick={() => setShowDelete(true)}
                    disabled={busy}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                    Delete component
                  </button>
                </div>
              </section>

              {latest ? (
                <ImpactCard
                  impact={{
                    ...(shownPrediction?.impact || latest.impact || {}),
                    recommendation: latest.recommendation,
                  }}
                  title="Impact of this recommendation"
                  compact
                />
              ) : null}
            </div>
          </div>

        </div>
      ) : null}

      {tab === 'passport' ? (
        <div className="space-y-5">
          <section className="card overflow-hidden">
            <div className="bg-navy-900 p-6 text-white sm:flex sm:items-center sm:justify-between">
              <div>
                <span className="text-[0.65rem] font-semibold uppercase tracking-widest text-accent-light">
                  Digital Component Passport
                </span>
                <h2 className="mt-1 font-mono text-2xl font-extrabold">{component.component_id}</h2>
                <p className="mt-1 text-sm text-navy-200">
                  {component.component_type} &middot; {materialWithGrade(component.material, component.material_grade_label)}
                </p>
                <p className="text-xs text-navy-300">Serial number: {component.serial_number}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <StatusBadge status={component.current_status} />
                  <RecommendationBadge recommendation={latest?.recommendation} />
                  <HealthBadge score={component.health_score} />
                </div>
              </div>
              <div className="mt-4 flex flex-col items-center rounded-xl bg-white p-3 sm:mt-0">
                <QRCodeDisplay
                  componentId={component.component_id}
                  dataUri={passport?.qr_data_uri}
                  size={140}
                  showActions={false}
                />
              </div>
            </div>
            <div className="no-print flex flex-wrap gap-2 border-t border-steel-200 bg-steel-50 px-5 py-3">
              <button type="button" className="btn-secondary btn-sm" onClick={() => window.print()}>
                <Printer className="h-4 w-4" aria-hidden="true" />
                Print passport label
              </button>
              <Link to={`/passport/${component.component_id}`} target="_blank" className="btn-ghost btn-sm">
                Open mobile scan view &rarr;
              </Link>
            </div>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            {passport?.dpp ? <PassportIdentity dpp={passport.dpp} /> : null}
            {passport?.standards_basis ? <StandardsBasis standards={passport.standards_basis} /> : null}
          </div>

          {passport?.quality_certificate ? (
            <QualityCertificateCard certificate={passport.quality_certificate} />
          ) : null}
        </div>
      ) : null}

      {tab === 'material' ? <TabBody missing={!profile}><MaterialProfileCard profile={profile} /></TabBody> : null}

      {tab === 'life' ? (
        <TabBody missing={!assessment && !forecast}>
          <div className="space-y-5">
            <LifeProjectionCard life={assessment} />
            <EarlyWarningCard forecast={forecast} />
          </div>
        </TabBody>
      ) : null}

      {tab === 'sensors' ? (
        <FieldDataCard
          componentId={component.component_id}
          onChanged={() => {
            refresh();
            refreshLife();
          }}
        />
      ) : null}

      {tab === 'scenarios' && FIELD_TYPES.includes(component.component_type) ? (
        <ScenarioCard
          componentId={component.component_id}
          scenarios={life?.scenarios || []}
          onDelete={async (scenarioId) => {
            try {
              await simulationApi.deleteScenario(scenarioId);
              refreshLife();
            } catch (err) {
              setActionError(err);
            }
          }}
        />
      ) : null}

      {/* ------------------------------------------------- service history */}
      {tab === 'service' ? (
        <section className="card">
          <header className="card-header">
            <div>
              <h2 className="card-title">Service history</h2>
              <p className="mt-0.5 text-xs text-steel-500">
                {events.length} recorded events, newest first.
              </p>
            </div>
            <button type="button" className="btn-accent btn-sm" onClick={() => setShowEventForm(true)}>
              Add event
            </button>
          </header>
          <div className="card-body">
            <ServiceTimeline
              events={events}
              emptyAction={
                <button type="button" className="btn-accent" onClick={() => setShowEventForm(true)}>
                  Record the first event
                </button>
              }
            />
          </div>
        </section>
      ) : null}

      {/* ---------------------------------------------------- assessments */}
      {tab === 'assessments' ? (
        <section className="card">
          <header className="card-header">
            <div>
              <h2 className="card-title">AI assessment history</h2>
              <p className="mt-0.5 text-xs text-steel-500">
                Every assessment is stored immutably; nothing is overwritten.
              </p>
            </div>
            <button type="button" className="btn-accent btn-sm" onClick={runAssessment} disabled={predicting}>
              {predicting ? 'Assessing...' : 'Run new assessment'}
            </button>
          </header>
          <div className="card-body">
            <PredictionTimeline predictions={predictions} />
          </div>
        </section>
      ) : null}

      {/* ---------------------------------------------------------- audit */}
      {tab === 'audit' ? (
        <section className="card">
          <header className="card-header">
            <div>
              <h2 className="card-title">Audit trail</h2>
              <p className="mt-0.5 text-xs text-steel-500">
                SHA-256 chain entries recorded against this component.
              </p>
            </div>
            <Link to="/audit" className="btn-ghost btn-sm">
              Verify full chain
            </Link>
          </header>
          <div className="card-body">
            <AuditTimeline entries={auditEntries} showEntity={false} />
          </div>
        </section>
      ) : null}

      {/* --------------------------------------------------------- modals */}
      <Modal
        open={showInspection}
        onClose={() => setShowInspection(false)}
        title="Record a measured inspection"
        description={`What you measured on ${component.component_id}. The inspection score is computed from it.`}
        size="lg"
      >
        <InspectionForm
          component={component}
          onSaved={() => {
            setShowInspection(false);
            refresh();
            refreshLife();
          }}
          onCancel={() => setShowInspection(false)}
        />
      </Modal>

      <Modal
        open={showEventForm}
        onClose={() => setShowEventForm(false)}
        title="Record a service event"
        description={`Adds a dated entry to the lifecycle history of ${component.component_id}.`}
        size="lg"
      >
        <ServiceEventForm
          component={component}
          onCreated={() => {
            setShowEventForm(false);
            refresh();
            setTab('service');
          }}
          onCancel={() => setShowEventForm(false)}
        />
      </Modal>

      <ConfirmModal
        open={showDelete}
        onClose={() => setShowDelete(false)}
        onConfirm={removeComponent}
        title={`Delete ${component.component_id}?`}
        description="The component and its dependent records are removed. The audit chain is append-only, so the deletion itself stays recorded and prior history remains verifiable."
        confirmLabel="Delete component"
        destructive
        busy={busy}
      />
    </div>
  );
}

/** Shows a loading hint while the life assessment is still arriving. */
function TabBody({ missing, children }) {
  if (missing) return <Loading label="Loading assessment..." />;
  return children;
}
