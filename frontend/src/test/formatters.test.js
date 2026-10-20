import { describe, expect, it } from 'vitest';
import {
  cx,
  formatAge,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  healthBand,
  humanise,
  shortHash,
  materialWithGrade,
} from '../utils/formatters';
import { RECOMMENDATIONS, SAFETY_CRITICAL_TYPES, isSafetyCritical } from '../utils/constants';

describe('formatters', () => {
  it('formats numbers and falls back safely', () => {
    expect(formatNumber(1234)).toBe('1,234');
    expect(formatNumber(null)).toBe('-');
    expect(formatNumber(undefined, 'n/a')).toBe('n/a');
  });

  it('formats percentages from 0-1 probabilities', () => {
    expect(formatPercent(0.923, 1)).toBe('92.3%');
    expect(formatPercent(1)).toBe('100%');
    expect(formatPercent(null)).toBe('-');
  });

  it('formats prototype currency with the supplied symbol', () => {
    expect(formatCurrency(45000, 'Rs.', { compact: false })).toBe('Rs. 45,000');
    expect(formatCurrency(null)).toBe('-');
  });

  it('formats dates and ages', () => {
    expect(formatDate('2018-04-12')).toBe('12 Apr 2018');
    expect(formatDate('not-a-date')).toBe('-');
    expect(formatAge(5.24)).toBe('5.2 yrs');
  });

  it('humanises enum values', () => {
    expect(humanise('UNDER_INSPECTION')).toBe('Under Inspection');
    expect(humanise('CONTINUE_USING')).toBe('Continue Using – No Changes Required');
    expect(humanise('COMPONENT_RECOVERY')).toBe('Component Recovery');
    expect(humanise('MATERIAL_RECOVERY')).toBe('Material Recovery');
    expect(humanise('DISPOSE')).toBe('Dispose');
    // Legacy codes (e.g. read back from the audit chain) show the new names.
    expect(humanise('REUSE')).toBe('Continue Using – No Changes Required');
    expect(humanise('RECYCLE')).toBe('Material Recovery');
    expect(humanise(null)).toBe('-');
  });

  it('truncates hashes for display', () => {
    const hash = 'a'.repeat(64);
    expect(shortHash(hash)).toBe(`${'a'.repeat(8)}...${'a'.repeat(6)}`);
    expect(shortHash('short')).toBe('short');
  });

  it('maps health scores to bands', () => {
    expect(healthBand(95).label).toBe('EXCELLENT');
    expect(healthBand(72).label).toBe('GOOD');
    expect(healthBand(60).label).toBe('FAIR');
    expect(healthBand(40).label).toBe('POOR');
    expect(healthBand(10).label).toBe('CRITICAL');
    expect(healthBand(null).label).toBe('NOT ASSESSED');
  });

  it('joins class names, skipping falsy values', () => {
    expect(cx('a', false, undefined, 'b')).toBe('a b');
  });
});

describe('domain constants', () => {
  it('lists the four categories in decision-flow order, plus abstention', () => {
    expect(RECOMMENDATIONS).toEqual([
      'CONTINUE_USING',
      'COMPONENT_RECOVERY',
      'MATERIAL_RECOVERY',
      'DISPOSE',
      'DEFER_TO_INSPECTION',
    ]);
  });

  it('shows the material with its recorded grade, or Not Determined', () => {
    expect(materialWithGrade('Steel', null)).toBe('Steel - Grade: Not Determined');
    expect(materialWithGrade('Cast Iron', 'Ductile iron')).toBe('Cast Iron - Grade: Ductile iron');
  });

  it('flags exactly the safety-critical component types', () => {
    expect(SAFETY_CRITICAL_TYPES).toEqual(['Steel Rope', 'Brake', 'Governor']);
    expect(isSafetyCritical('Steel Rope')).toBe(true);
    expect(isSafetyCritical('Brake')).toBe(true);
    expect(isSafetyCritical('Governor')).toBe(true);
    expect(isSafetyCritical('Motor')).toBe(false);
    expect(isSafetyCritical('Door Operator')).toBe(false);
  });
});
