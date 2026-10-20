import { Brain, CheckCircle2, CircleHelp, Recycle, ShieldAlert, Sparkles, XCircle } from 'lucide-react';
import { RECOMMENDATION_STYLE, recommendationStyle } from '../utils/constants';
import { cx, formatDateTime, humanise } from '../utils/formatters';
import ConfidenceBar, { ProbabilityBreakdown } from './ConfidenceBar';
import FactorList, { HealthBreakdown, ShapFactorList } from './FactorList';
import { HealthBar } from './HealthBadge';
import { EarlyWarningIndicator } from './EarlyWarning';

/**
 * Shown when the abstention rule (app.ml.abstention) overrode the model's own
 * best guess. Distinct from the safety gate: this is the model saying it
 * does not know, not a rule about which component types always need a human.
 */
function AbstentionNotice({ prediction }) {
  if (!prediction?.abstained) return null;
  return (
    <div className="flex gap-3 rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-900">
      <CircleHelp className="mt-0.5 h-5 w-5 shrink-0 text-violet-600" aria-hidden="true" />
      <div className="space-y-1">
        <p className="font-semibold">
          The model deferred to inspection instead of guessing.
        </p>
        <p className="text-xs text-violet-800">
          Its own best guess was <strong>{humanise(prediction.underlying_recommendation)}</strong>
          {prediction.prediction_set?.length > 1
            ? `, but ${prediction.prediction_set.map(humanise).join(' / ')} were all plausible enough that a wrong single answer was more likely than usual.`
            : ' at low confidence.'}
        </p>
      </div>
    </div>
  );
}

/** The mandatory safety-gate banner for safety-critical components. */
export function SafetyGate({ prediction }) {
  if (!prediction?.safety_flag) {
    return (
      <div className="rounded-lg border border-steel-200 bg-steel-50 px-4 py-3 text-sm text-steel-600">
        <span className="font-semibold text-navy-800">Safety gate:</span>{' '}
        No mandatory safety flag for this component type.
      </div>
    );
  }

  return (
    <div className="safety-banner" role="alert">
      <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
      <div className="space-y-1">
        <p className="text-base font-extrabold uppercase tracking-wide">
          {prediction.safety_message || 'MANDATORY HUMAN INSPECTION'}
        </p>
        <p className="font-medium">
          AI recommendation: {humanise(prediction.recommendation)}. Human inspection is required
          before this recommendation is acted on.
        </p>
        <p className="text-xs font-normal text-red-700">
          This component type is safety-critical. The AI output is advisory only and is never an
          approval, certification or authorisation to operate an elevator.
        </p>
      </div>
    </div>
  );
}

/**
 * The full "AI Circular Intelligence" result panel.
 *
 * Renders recommendation, confidence, health score, ranked explanation factors
 * and the safety gate - in that order, so the safety requirement is never
 * further down the page than the recommendation it qualifies.
 */
export default function PredictionCard({
  prediction,
  title = 'AI Circular Intelligence',
  showBreakdown = true,
  showProbabilities = true,
  compact = false,
}) {
  if (!prediction) return null;

  const style = recommendationStyle(prediction.recommendation) || RECOMMENDATION_STYLE.DISPOSE;

  return (
    <section className="card animate-fade-in overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-steel-200 bg-navy-900 px-5 py-4 text-white">
        <div className="flex items-center gap-2.5">
          <Brain className="h-5 w-5 text-accent-light" aria-hidden="true" />
          <div>
            <h2 className="text-sm font-bold uppercase tracking-widest">{title}</h2>
            <p className="text-[0.7rem] text-navy-200">
              {prediction.model_version}
              {prediction.predicted_at ? ` - ${formatDateTime(prediction.predicted_at)}` : ''}
            </p>
          </div>
        </div>
        {!prediction.model_available ? (
          <span className="badge bg-amber-200 text-amber-900">Heuristic fallback - model missing</span>
        ) : (
          <span className="badge bg-navy-700 text-navy-100">Synthetic-data model</span>
        )}
      </header>

      <div className="grid grid-cols-1 gap-5 p-5 lg:grid-cols-3">
        {/* ------------------------------------------------ headline result */}
        <div className="space-y-4 lg:col-span-1">
          <div
            className="rounded-xl border-2 p-4 text-center"
            style={{ borderColor: style.hex, backgroundColor: `${style.hex}0f` }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-steel-500">
              Recommendation
            </p>
            <p className="mt-1 text-2xl font-extrabold tracking-tight" style={{ color: style.hex }}>
              {humanise(prediction.recommendation)}
            </p>
            <p className="mt-1 text-xs text-steel-600">{prediction.recommendation_text || style.description}</p>
          </div>

          <DecisionFlowSteps flow={prediction.decision_flow} />
          <CircularStrategyNote strategy={prediction.circular_strategy} />

          <div className="rounded-xl border border-steel-200 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-steel-500">
              Health score
            </p>
            <HealthBar score={prediction.health_score} />
          </div>

          <div className="rounded-xl border border-steel-200 p-4">
            <ConfidenceBar confidence={prediction.confidence} />
          </div>

          {showProbabilities && prediction.probabilities ? (
            <div className="rounded-xl border border-steel-200 p-4">
              <ProbabilityBreakdown probabilities={prediction.probabilities} />
            </div>
          ) : null}
        </div>

        {/* ------------------------------------------------- explainability */}
        <div className="space-y-4 lg:col-span-2">
          <AbstentionNotice prediction={prediction} />
          <SafetyGate prediction={prediction} />
          <EarlyWarningIndicator forecast={prediction.early_warning} />

          <div>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-navy-900">
              <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
              Key factors behind this recommendation
            </h3>
            <FactorList factors={prediction.key_factors} />
          </div>

          {prediction.shap_factors?.length ? (
            <div>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-navy-900">
                <Sparkles className="h-4 w-4 text-cyan-600" aria-hidden="true" />
                SHAP attribution (independent second method)
              </h3>
              <ShapFactorList factors={prediction.shap_factors} />
            </div>
          ) : null}

          <p className="text-[0.7rem] text-steel-400">{prediction.explanation_method}</p>

          {showBreakdown && prediction.health_breakdown?.length ? (
            <details className={cx('rounded-lg border border-steel-200 p-4', compact && 'hidden')}>
              <summary className="cursor-pointer text-sm font-semibold text-navy-800">
                How the health score was calculated
              </summary>
              <div className="mt-3">
                <HealthBreakdown breakdown={prediction.health_breakdown} />
                <p className="mt-3 text-[0.7rem] text-steel-400">{prediction.health_methodology}</p>
              </div>
            </details>
          ) : null}

          <div className="space-y-1 rounded-lg bg-steel-100 px-4 py-3 text-[0.7rem] text-steel-600">
            <p>
              <strong className="text-navy-800">Advisory only.</strong> {prediction.disclaimer}
            </p>
            <p>
              <strong className="text-navy-800">Data.</strong> {prediction.data_notice}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/**
 * The decision flow, gate by gate: suitable for its current application ->
 * usable sub-components -> useful material -> dispose. Only present on a
 * fresh assessment (stored history rows do not carry it).
 */
function DecisionFlowSteps({ flow }) {
  if (!flow?.steps?.length) return null;
  const parts = flow.subcomponents?.parts || [];

  return (
    <div className="rounded-xl border border-steel-200 p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-steel-500">
        How the category was decided
      </p>
      <ol className="space-y-2">
        {flow.steps.map((step) => (
          <li key={step.gate} className="flex gap-2 text-xs">
            {step.passed ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-steel-400" aria-hidden="true" />
            )}
            <div>
              <p className="font-semibold text-navy-900">
                {step.gate} <span className="font-normal text-steel-500">{step.passed ? 'Yes' : 'No'}</span>
              </p>
              <p className="text-[0.7rem] leading-snug text-steel-600">{step.evidence}</p>
            </div>
          </li>
        ))}
      </ol>
      {parts.length ? (
        <p className="mt-2 text-[0.7rem] text-steel-600">
          <strong className="text-navy-800">Sub-components for the recorded grade:</strong> {parts.join(', ')}
        </p>
      ) : null}
      {!flow.applied ? (
        <p className="mt-2 text-[0.7rem] text-violet-700">
          Not applied: the model deferred to inspection. Shown for reference only.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Where the recommended category sits on the circular-economy R-ladder.
 *
 * A note beneath the recommendation, never a replacement for it. The ladder
 * rungs that would move, restore or supply a complete component elsewhere are
 * not offered by this platform, so the rung simply follows the category.
 */
function CircularStrategyNote({ strategy }) {
  if (!strategy?.rung) return null;

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
      <div className="flex items-center gap-2">
        <Recycle className="h-4 w-4 shrink-0 text-emerald-700" aria-hidden="true" />
        <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
          Circular-economy position
        </p>
      </div>
      <p className="mt-1.5 text-sm font-bold text-emerald-900">
        {strategy.rung} {strategy.name}
      </p>
      {strategy.safety_note ? (
        <p className="mt-1 text-[0.7rem] leading-snug text-emerald-800">{strategy.safety_note}</p>
      ) : null}
    </div>
  );
}
