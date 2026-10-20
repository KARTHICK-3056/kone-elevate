/**
 * Shared vocabulary and presentation constants.
 *
 * These mirror `backend/app/utils/enums.py`. The backend also serves them at
 * `GET /api/v1/meta/enums`; these copies keep the UI usable (menus, colours,
 * empty states) even while the API is unreachable.
 */

export const RECOMMENDATIONS = [
  'CONTINUE_USING',
  'COMPONENT_RECOVERY',
  'MATERIAL_RECOVERY',
  'DISPOSE',
  'DEFER_TO_INSPECTION',
];

/** The display names of the four categories, exactly as they are shown. */
export const RECOMMENDATION_LABELS = {
  CONTINUE_USING: 'Continue Using – No Changes Required',
  COMPONENT_RECOVERY: 'Component Recovery',
  MATERIAL_RECOVERY: 'Material Recovery',
  DISPOSE: 'Dispose',
  DEFER_TO_INSPECTION: 'Defer to Inspection',
};

/**
 * Codes stored before the categories were renamed (e.g. in the append-only
 * audit chain, which is never rewritten). Read them as the new categories.
 */
export const LEGACY_RECOMMENDATIONS = {
  REUSE: 'CONTINUE_USING',
  REFURBISH: 'COMPONENT_RECOVERY',
  RECYCLE: 'MATERIAL_RECOVERY',
};

/** A recommendation code in the current vocabulary (legacy codes mapped). */
export const canonicalRecommendation = (code) => (code ? (LEGACY_RECOMMENDATIONS[code] ?? code) : code);

/** Display name for a recommendation code, or null when it is not one. */
export const recommendationLabel = (code) => RECOMMENDATION_LABELS[canonicalRecommendation(code)] ?? null;

export const COMPONENT_TYPES = [
  'Motor',
  'Steel Rope',
  'Brake',
  'Governor',
  'Door Operator',
  'Sheave',
];

export const MATERIALS = ['Steel', 'Cast Iron', 'Aluminum', 'Copper', 'Composite'];

export const LIFECYCLE_STATUSES = [
  'ACTIVE',
  'UNDER_INSPECTION',
  'REMOVED',
  'RECOVERED',
  'PART_RECOVERY',
  'MATERIAL_RECOVERED',
  'DISPOSED',
];

export const SERVICE_EVENT_TYPES = [
  'INSTALLATION',
  'INSPECTION',
  'MAINTENANCE',
  'REPAIR',
  'MODERNIZATION',
  'REMOVAL',
];

/** Shown wherever a material grade is not on record. Never replaced by a guess. */
export const GRADE_NOT_DETERMINED = 'Not Determined';

export const SAFETY_CRITICAL_TYPES = ['Steel Rope', 'Brake', 'Governor'];

export const SAFETY_GATE_MESSAGE = 'MANDATORY HUMAN INSPECTION';

export const RECOMMENDATION_DISCLAIMER =
  'AI-assisted end-of-use recommendation. Advisory only - this is not a certification, approval or authorisation to operate an elevator.';

export const SYNTHETIC_DATA_NOTICE =
  'Prototype uses synthetic degradation data. Production deployment requires validation against real historical component service, inspection, sensor and removal records.';

export const PROTOTYPE_ESTIMATE_LABEL = 'Prototype estimate';

/** Tailwind-friendly colour tokens per recommendation category. */
export const RECOMMENDATION_STYLE = {
  CONTINUE_USING: {
    label: RECOMMENDATION_LABELS.CONTINUE_USING,
    hex: '#0f9d58',
    badge: 'bg-emerald-100 text-emerald-800 border border-emerald-200',
    dot: 'bg-emerald-500',
    description:
      'The component is still suitable for its current device and application and can continue operating there without modification.',
  },
  COMPONENT_RECOVERY: {
    label: RECOMMENDATION_LABELS.COMPONENT_RECOVERY,
    hex: '#1a73e8',
    badge: 'bg-blue-100 text-blue-800 border border-blue-200',
    dot: 'bg-blue-500',
    description:
      'Recover usable sub-components from the existing component after inspection and testing. Suitable recovered parts may be redirected to lower-demand applications where technically appropriate. The complete component is not supplied again.',
  },
  MATERIAL_RECOVERY: {
    label: RECOMMENDATION_LABELS.MATERIAL_RECOVERY,
    hex: '#f4a300',
    badge: 'bg-amber-100 text-amber-900 border border-amber-200',
    dot: 'bg-amber-500',
    description:
      'The component and its parts are no longer suitable for use. Recover useful material from the end-of-life component through the appropriate process.',
  },
  DISPOSE: {
    label: RECOMMENDATION_LABELS.DISPOSE,
    hex: '#d93025',
    badge: 'bg-red-100 text-red-800 border border-red-200',
    dot: 'bg-red-500',
    description:
      'No technically suitable option exists for continued use, component recovery or material recovery. Dispose of the component through the appropriate route.',
  },
  DEFER_TO_INSPECTION: {
    label: RECOMMENDATION_LABELS.DEFER_TO_INSPECTION,
    hex: '#7c3aed',
    badge: 'bg-violet-100 text-violet-800 border border-violet-200',
    dot: 'bg-violet-500',
    description:
      'The model abstained: its confidence was low or the plausible-class set was ambiguous. A human inspection decides, not the AI.',
  },
};

export const HEALTH_BANDS = [
  { min: 85, label: 'EXCELLENT', hex: '#0f9d58', badge: 'bg-emerald-100 text-emerald-800' },
  { min: 70, label: 'GOOD', hex: '#34a853', badge: 'bg-green-100 text-green-800' },
  { min: 55, label: 'FAIR', hex: '#f4a300', badge: 'bg-amber-100 text-amber-900' },
  { min: 35, label: 'POOR', hex: '#f06423', badge: 'bg-orange-100 text-orange-900' },
  { min: 0, label: 'CRITICAL', hex: '#d93025', badge: 'bg-red-100 text-red-800' },
];

export const IMPACT_STYLE = {
  positive: { label: 'Positive', badge: 'bg-emerald-100 text-emerald-800' },
  low: { label: 'Low', badge: 'bg-steel-100 text-steel-700' },
  moderate: { label: 'Moderate', badge: 'bg-amber-100 text-amber-900' },
  high: { label: 'High', badge: 'bg-orange-100 text-orange-900' },
  critical: { label: 'Critical', badge: 'bg-red-100 text-red-800' },
};

export const STATUS_STYLE = {
  ACTIVE: 'bg-emerald-100 text-emerald-800',
  UNDER_INSPECTION: 'bg-amber-100 text-amber-900',
  REMOVED: 'bg-steel-200 text-steel-700',
  RECOVERED: 'bg-cyan-100 text-cyan-800',
  PART_RECOVERY: 'bg-blue-100 text-blue-800',
  MATERIAL_RECOVERED: 'bg-amber-100 text-amber-900',
  DISPOSED: 'bg-red-100 text-red-800',
};

export const CHART_COLORS = ['#0f9d58', '#1a73e8', '#f4a300', '#d93025', '#0aa2c0', '#6a89bd', '#8593aa', '#2b406e'];

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

/** Style for a recommendation code (legacy codes mapped). */
export const recommendationStyle = (code) => RECOMMENDATION_STYLE[canonicalRecommendation(code)];

export const isSafetyCritical = (componentType) => SAFETY_CRITICAL_TYPES.includes(componentType);
