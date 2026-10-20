import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LifeProjectionCard, MaterialProfileCard } from '../components/LifeProjection';
// Captured from GET /api/v1/passports/KE-SHE-000003/life on the seeded demo data.
import sheave from './fixtures/life-sheave.json';

// ResponsiveContainer measures its parent, which jsdom reports as 0x0.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const unsupported = {
  supported: false,
  component_type: 'Handrail',
  reason: 'The usage-adjusted life model currently covers the registry component types only.',
};

// The sensor card fetches over the network, which jsdom cannot do.
vi.mock('../components/FieldDataCard', () => ({ default: () => <div>Sensor and controller data</div> }));

vi.mock('../hooks/useComponents', () => ({
  useComponent: () => ({
    component: {
      component_id: 'KE-SHE-000003',
      serial_number: 'SH12-TEST',
      component_type: 'Sheave',
      material: 'Cast Iron',
      current_status: 'ACTIVE',
      component_age: 29.5,
      latest_prediction: null,
    },
    events: [],
    predictions: [],
    loading: false,
    error: null,
    refresh: () => {},
  }),
  useLifeAssessment: () => ({ life: sheave, error: null, refresh: () => {} }),
  usePassport: () => ({ passport: null, loading: false, error: null, refresh: () => {} }),
}));

describe('Grade cost comparison', () => {
  it('ranks every grade by cost per year and marks the most cost-effective one', () => {
    render(<MaterialProfileCard profile={sheave.material_profile} />);
    expect(screen.getByText('Cost comparison by grade')).toBeInTheDocument();
    expect(screen.getByText(/would cost Rs\. [\d,]+ less per year of service/)).toBeInTheDocument();

    const table = screen.getByText('Cost comparison by grade').parentElement.querySelector('table');
    const rows = [...table.querySelectorAll('tbody tr')];
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('Most cost-effective');
    expect(rows[0]).toHaveTextContent('Ductile');
    expect(rows.find((row) => row.textContent.includes('This component'))).toHaveTextContent('Grey');
  });
});

describe('Life projection cards', () => {
  it('render the material breakdown and the design-vs-actual projection', () => {
    render(<MaterialProfileCard profile={sheave.material_profile} />);
    render(<LifeProjectionCard life={sheave.life_assessment} />);

    expect(screen.getByText('Material composition and characteristics')).toBeInTheDocument();
    // No grade is recorded for this sheave: the industry-standard grade is
    // shown, and clearly marked as assumed.
    expect(screen.getByText('Industry standard - assumed')).toBeInTheDocument();
    expect(screen.getAllByText(/industry standard - assumed, not recorded/).length).toBeGreaterThan(0);
    expect(screen.getByText('Grey cast iron')).toBeInTheDocument();
    expect(screen.getByText('Pre-emptive life projection')).toBeInTheDocument();
    expect(screen.getByText(/Wearing at/)).toBeInTheDocument();
    // Plain-language ages: expected life, actual age, usage-based age.
    for (const label of ['Expected life', 'Actual age', 'Usage-based age', 'Life used', 'Remaining life', 'Projected total life']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('Enters replace band (80% used)')).toBeInTheDocument();
    expect(screen.getAllByText(/KONE published API/).length).toBeGreaterThan(0);
  });

  it('words the life change from its sign, not from the rate today', () => {
    // Worn fast today, but light past use still leaves total life longer.
    const mixed = {
      ...sheave.life_assessment,
      ageing_rate: 1.3,
      projection: { ...sheave.life_assessment.projection, life_change_years: 0.5 },
    };
    render(<LifeProjectionCard life={mixed} />);
    expect(screen.getByText(/extending its life by 0.5 years/)).toBeInTheDocument();
    expect(screen.queryByText(/shortening its life/)).not.toBeInTheDocument();
  });

  it('explains an uncovered component type instead of rendering nothing', () => {
    render(<LifeProjectionCard life={unsupported} />);
    expect(screen.getByText('Pre-emptive life projection')).toBeInTheDocument();
    expect(screen.getByText(/registry component types only/)).toBeInTheDocument();
  });
});

describe('ComponentDetails', () => {
  const renderAt = async (url) => {
    const { default: ComponentDetails } = await import('../pages/ComponentDetails');
    render(
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/components/:componentId" element={<ComponentDetails />} />
        </Routes>
      </MemoryRouter>,
    );
  };

  it('keeps the overview short and links to the material and life tabs', async () => {
    await renderAt('/components/KE-SHE-000003');
    expect(screen.getByText('Component record')).toBeInTheDocument();
    expect(screen.queryByText('Material composition and characteristics')).not.toBeInTheDocument();
    expect(screen.getByText('Projected total life')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Material/ }));
    expect(screen.getByText('Material composition and characteristics')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /Overview/ }));
    fireEvent.click(screen.getByText('Projected total life').closest('button'));
    expect(screen.getByText('Pre-emptive life projection')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Life & forecast/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('opens the tab named in the link', async () => {
    await renderAt('/components/KE-SHE-000003?tab=life');
    expect(screen.getByText('Pre-emptive life projection')).toBeInTheDocument();
    expect(screen.queryByText('Component record')).not.toBeInTheDocument();
  });
});

describe('Pre-emptive issue forecast', () => {
  it('shows an indication after an assessment and expands into the evidence', async () => {
    const { fireEvent } = await import('@testing-library/react');
    const { EarlyWarningIndicator } = await import('../components/EarlyWarning');
    const forecast = (await import('./fixtures/early-warning-rope.json')).default;

    render(<EarlyWarningIndicator forecast={forecast} />);
    expect(screen.getByText('Pre-emptive issue forecast')).toBeInTheDocument();
    expect(screen.getByText(forecast.headline)).toBeInTheDocument();
    expect(screen.queryByText('Independent signals checked')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /evidence, justification and measures/ }));
    expect(screen.getAllByText('Independent signals checked').length).toBe(forecast.issues.length);
    expect(screen.getAllByText('Recommended measures before it arrives').length).toBe(forecast.issues.length);
    expect(screen.getByText('Every indicator monitored')).toBeInTheDocument();
  });

  it('says so plainly when nothing is predicted', async () => {
    const { EarlyWarningCard } = await import('../components/EarlyWarning');
    render(
      <EarlyWarningCard
        forecast={{ supported: true, headline: 'No issue predicted within the next 3 years at current trends.', issues: [], indicators: [], method: '', lead_time_days: 60 }}
      />,
    );
    expect(screen.getByText(/No issue predicted/)).toBeInTheDocument();
  });
});
