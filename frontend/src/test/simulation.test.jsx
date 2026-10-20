import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
// Captured from app.simulation.engine: 1 year at 460 kg, then 8 years at 800 kg.
import fixture from './fixtures/simulation.json';

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// jsdom has no WebGL; the scene is exercised in the browser, not here.
vi.mock('../components/ElevatorScene', () => ({
  default: ({ visual }) => (
    <div data-testid="scene">
      load {visual.loadKg} motor {visual.bands?.Motor}
    </div>
  ),
}));

const setLoad = vi.fn();
const setRunning = vi.fn();
const saveScenario = vi.fn(async () => ({ id: 1, name: 'Heavier traffic' }));
let focus = null;

vi.mock('../api/client', () => ({
  componentsApi: {
    list: vi.fn(async ({ component_type: type }) => ({
      items: type === 'Motor' ? [{ component_id: 'KE-MOT-000003', component_type: 'Motor', component_age: 9.4 }] : [],
    })),
  },
}));

vi.mock('../hooks/useSimulation', () => ({
  SPEEDS: [{ months: 3, label: '3 months / step' }],
  useSimulation: () => ({
    reference: fixture.reference,
    load: 800,
    setLoad,
    speed: 3,
    setSpeed: () => {},
    running: false,
    setRunning,
    get results() {
      return { ...fixture.advance.results, focus };
    },
    series: fixture.advance.series,
    events: fixture.events,
    error: null,
    busy: false,
    step: () => {},
    reset: () => {},
    startFrom: vi.fn(),
    saveScenario,
  }),
}));

describe('Simulation page', () => {
  it('takes only the load as input and shows the 13 derived parameters', async () => {
    const { default: Simulation } = await import('../pages/Simulation');
    render(
      <MemoryRouter>
        <Simulation />
      </MemoryRouter>,
    );

    expect(screen.getByText('Your input: average load per trip')).toBeInTheDocument();
    expect(screen.getByText('The 13 model parameters - KONE API first')).toBeInTheDocument();
    const table = screen.getByText('The 13 model parameters - KONE API first').closest('section');
    expect(within(table).getAllByRole('row').length).toBe(1 + 13);
    // KONE API first; only vibration, temperature and age are simulated.
    const simulatedRows = within(table)
      .getAllByRole('row')
      .filter((row) => /^Simulated/.test(row.lastChild.textContent));
    expect(simulatedRows.map((row) => row.firstChild.textContent).sort()).toEqual(
      ['Age (years)', 'Temperature (C)', 'Vibration (mm/s)'].sort(),
    );
    // Eight rows from KONE; the load row reads "Your input" here because the
    // run's 800 kg differs from KONE's 460 kg default.
    expect(within(table).getAllByText('KONE API').length).toBe(7);
    // A KONE row shows only its KONE API tag - no secondary "then ..." tag.
    expect(within(table).queryByText(/^then /)).toBeNull();
    expect(within(table).getByText('Your input')).toBeInTheDocument();

    // The 3D model is driven by the same results.
    expect(screen.getByTestId('scene')).toHaveTextContent('load 800');

    fireEvent.change(screen.getByLabelText('Average load per trip in kilograms'), { target: { value: '300' } });
    expect(setLoad).toHaveBeenCalledWith(300);

    fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    expect(setRunning).toHaveBeenCalledWith(true);
  });

  it('says where its numbers come from', async () => {
    const { default: Simulation } = await import('../pages/Simulation');
    render(
      <MemoryRouter>
        <Simulation />
      </MemoryRouter>,
    );
    expect(screen.getByText(/KONE API source right now/)).toHaveTextContent('recorded example responses');
    expect(screen.getByText('Calibration reference')).toBeInTheDocument();
    expect(screen.getByText('Did the pre-analysis work?')).toBeInTheDocument();
  });
});

describe('Simulation from a real component', () => {
  it('labels the real part and saves the scenario to its passport', async () => {
    focus = {
      component_id: 'KE-MOT-000003',
      component_type: 'Motor',
      location: 'Chennai',
      historical_load_kg: 90,
      implied_load: { load_kg: 90, alternative_load_kg: 880 },
      starting_wear: 0.62,
      calibration: { note: 'Calibrated to this unit.' },
      note: 'Starts from its real record.',
    };
    const { default: Simulation } = await import('../pages/Simulation');
    render(
      <MemoryRouter initialEntries={['/simulation?component=KE-MOT-000003']}>
        <Simulation />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Simulating KE-MOT-000003/)).toBeInTheDocument();
    expect(screen.getByText('Real record: KE-MOT-000003')).toBeInTheDocument();
    expect(screen.getAllByText('Simulated companion')).toHaveLength(3);

    fireEvent.change(screen.getByLabelText('Scenario name'), { target: { value: 'Heavier traffic' } });
    fireEvent.click(screen.getByRole('button', { name: /Save to passport/ }));
    expect(saveScenario).toHaveBeenCalledWith('Heavier traffic');
    expect(await screen.findByText(/Saved "Heavier traffic"/)).toBeInTheDocument();
    focus = null;
  });
});
