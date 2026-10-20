import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PredictionCard, { SafetyGate } from '../components/PredictionCard';
import HealthBadge, { RecommendationBadge } from '../components/HealthBadge';
import FactorList from '../components/FactorList';

const basePrediction = {
  recommendation: 'COMPONENT_RECOVERY',
  recommendation_label: 'Component Recovery',
  recommendation_text:
    'Recover usable sub-components from this motor after inspection and testing. The complete component is not supplied again.',
  decision_flow: {
    recommendation: 'COMPONENT_RECOVERY',
    label: 'Component Recovery',
    applied: true,
    steps: [
      { gate: 'Suitable for its current application?', passed: false, evidence: 'Classifier: 3% fit to continue.' },
      { gate: 'Usable individual sub-components recoverable?', passed: true, evidence: 'Parts judged serviceable.' },
    ],
    subcomponents: { possible: true, parts: [] },
  },
  confidence: 0.92,
  health_score: 78,
  health_band: 'GOOD',
  degradation_index: 0.22,
  safety_flag: false,
  safety_message: null,
  safety_note: 'No mandatory safety flag for this component type.',
  model_version: 'RF-v1.0-synthetic',
  model_available: true,
  probabilities: { CONTINUE_USING: 0.05, COMPONENT_RECOVERY: 0.92, MATERIAL_RECOVERY: 0.02, DISPOSE: 0.01 },
  key_factors: [
    {
      factor: 'Vibration',
      feature: 'vibration',
      impact: 'moderate',
      description: 'Vibration level is elevated but not severe.',
      value: 4.6,
      unit: 'mm/s RMS',
      model_importance: 0.09,
    },
  ],
  health_breakdown: [],
  health_methodology: 'Prototype health score requires engineering validation before production use.',
  explanation_method: 'Random Forest feature importance with envelope deviation. SHAP is not used.',
  disclaimer: 'AI-assisted end-of-use recommendation. Advisory only.',
  data_notice: 'Prototype uses synthetic degradation data.',
};

describe('PredictionCard', () => {
  it('renders the recommendation, confidence and health score', () => {
    render(<PredictionCard prediction={basePrediction} />);
    // The category appears in the headline panel and in the probability list.
    expect(screen.getAllByText('Component Recovery').length).toBeGreaterThan(1);
    expect(screen.getAllByText('92.0%').length).toBeGreaterThan(0);
    expect(screen.getByText('78.0')).toBeInTheDocument();
  });

  it('lists the explanation factors', () => {
    render(<PredictionCard prediction={basePrediction} />);
    expect(screen.getByText('Vibration')).toBeInTheDocument();
    expect(screen.getByText(/elevated but not severe/i)).toBeInTheDocument();
  });

  it('shows the advisory disclaimer and synthetic-data notice', () => {
    render(<PredictionCard prediction={basePrediction} />);
    expect(screen.getAllByText(/advisory only/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/synthetic degradation data/i).length).toBeGreaterThan(0);
  });

  it('shows the decision flow gate by gate and the component-aware text', () => {
    render(<PredictionCard prediction={basePrediction} />);
    expect(screen.getByText('How the category was decided')).toBeInTheDocument();
    expect(screen.getByText(/Suitable for its current application\?/)).toBeInTheDocument();
    expect(screen.getByText(/Recover usable sub-components from this motor/)).toBeInTheDocument();
  });

  it('never shows a removed category name', () => {
    render(<PredictionCard prediction={basePrediction} />);
    expect(document.body.textContent).not.toMatch(/\b(reuse|recycl\w*)\b/i);
  });

  it('never shows a safety banner for an ordinary component', () => {
    render(<PredictionCard prediction={basePrediction} />);
    expect(screen.queryByText('MANDATORY HUMAN INSPECTION')).not.toBeInTheDocument();
  });
});

describe('safety gate', () => {
  const rope = {
    ...basePrediction,
    recommendation: 'CONTINUE_USING',
    safety_flag: true,
    safety_message: 'MANDATORY HUMAN INSPECTION',
    safety_note:
      'AI recommendation: CONTINUE_USING. Human inspection required. This component type is safety-critical.',
  };

  it('shows the mandatory inspection banner even when the AI says Continue Using', () => {
    render(<SafetyGate prediction={rope} />);
    expect(screen.getByText('MANDATORY HUMAN INSPECTION')).toBeInTheDocument();
    expect(screen.getByText(/AI recommendation: Continue Using – No Changes Required/)).toBeInTheDocument();
    expect(screen.getByText(/human inspection is required/i)).toBeInTheDocument();
  });

  it('never claims approval or certification', () => {
    render(<SafetyGate prediction={rope} />);
    const text = document.body.textContent.toLowerCase();
    expect(text).not.toContain('approved for operation');
    expect(text).not.toContain('ai approved');
    expect(text).not.toContain('certified');
  });
});

describe('badges', () => {
  it('renders the health score and band', () => {
    render(<HealthBadge score={78} />);
    expect(screen.getByText('78')).toBeInTheDocument();
    expect(screen.getByText('GOOD')).toBeInTheDocument();
  });

  it('shows the exact category names, legacy codes included', () => {
    const { rerender } = render(<RecommendationBadge recommendation="CONTINUE_USING" />);
    expect(screen.getByText('Continue Using – No Changes Required')).toBeInTheDocument();
    rerender(<RecommendationBadge recommendation="REFURBISH" />);
    expect(screen.getByText('Component Recovery')).toBeInTheDocument();
    rerender(<RecommendationBadge recommendation="MATERIAL_RECOVERY" />);
    expect(screen.getByText('Material Recovery')).toBeInTheDocument();
    rerender(<RecommendationBadge recommendation="DISPOSE" />);
    expect(screen.getByText('Dispose')).toBeInTheDocument();
  });

  it('marks an unassessed component clearly', () => {
    render(<RecommendationBadge recommendation={null} />);
    expect(screen.getByText('Not assessed')).toBeInTheDocument();
  });
});

describe('FactorList', () => {
  it('handles an empty factor list gracefully', () => {
    render(<FactorList factors={[]} />);
    expect(screen.getByText(/no explanation factors/i)).toBeInTheDocument();
  });
});
