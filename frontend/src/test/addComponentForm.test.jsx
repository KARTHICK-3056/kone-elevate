import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  componentsApi: { create: vi.fn() },
  platformApi: {
    enums: vi.fn(async () => ({
      material_grades: {
        Brake: [
          {
            grade: 'cast_iron_drum_organic',
            label: 'Cast iron drum / plate with organic friction lining',
            designation: 'EN-GJL-250 drum, SAE J866 FF lining',
            grading_system: 'EN 1561 grey cast iron; SAE J866 friction coefficient code',
            materials: ['Cast Iron'],
          },
          { grade: 'steel_disc_sintered', label: 'Steel disc / plate with sintered metallic lining', materials: ['Steel'] },
        ],
      },
    })),
  },
}));

describe('Add component form - material grade', () => {
  it('offers only the grades valid for the type and material, with their designation, defaulting to the industry standard', async () => {
    const { default: AddComponentForm } = await import('../pages/partials/AddComponentForm');
    render(<AddComponentForm />);

    fireEvent.change(screen.getByLabelText(/Component type/), { target: { value: 'Brake' } });
    fireEvent.change(screen.getByLabelText(/^Material \*/), { target: { value: 'Cast Iron' } });

    const grade = await screen.findByLabelText('Material grade');
    expect(grade.value).toBe('');
    await screen.findByRole('option', { name: /organic friction lining/ });
    const options = [...grade.querySelectorAll('option')].map((option) => option.textContent);
    expect(options).toEqual([
      'Not recorded - use industry standard',
      'EN-GJL-250 drum, SAE J866 FF lining — Cast iron drum / plate with organic friction lining',
    ]);

    fireEvent.change(grade, { target: { value: 'cast_iron_drum_organic' } });
    expect(screen.getByText(/Graded under: EN 1561 grey cast iron/)).toBeInTheDocument();
  });

  it('no longer offers Guide Rail or Control Board as a component type', async () => {
    const { default: AddComponentForm } = await import('../pages/partials/AddComponentForm');
    render(<AddComponentForm />);
    const types = [...screen.getByLabelText(/Component type/).querySelectorAll('option')].map((o) => o.value);
    expect(types).not.toContain('Guide Rail');
    expect(types).not.toContain('Control Board');
    expect(types).toContain('Governor');
  });
});
