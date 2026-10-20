/**
 * Centralised API client.
 *
 * Every network call in the UI goes through this module so that base URL,
 * timeouts, the audit actor header and - crucially - error normalisation are
 * defined exactly once. Raw stack traces and internal messages are never shown
 * to a user; the interceptor converts every failure into a friendly message.
 */

import axios from 'axios';
import { enqueue } from '../offline/outbox';

export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

/** Where the bearer token lives between page loads. */
const TOKEN_KEY = 'kone-elevate.token';

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (token) => {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* Private browsing or blocked storage: the session still works, it
         just will not survive a reload. */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* nothing to do */
    }
  },
};

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  headers: { 'Content-Type': 'application/json' },
});

// The identity recorded against every change comes from this token, verified
// server-side. There is deliberately no client-supplied actor header any
// more: the backend ignores one entirely.
http.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Error shape the UI renders. */
export class ApiError extends Error {
  constructor(message, { status = 0, code = 'unknown_error', details = null, offline = false } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.offline = offline;
  }
}

function normaliseError(error) {
  // No response at all: the backend is down, blocked, or the request timed out.
  if (!error.response) {
    const timedOut = error.code === 'ECONNABORTED';
    return new ApiError(
      timedOut
        ? 'The request took too long. The backend may be busy - please try again.'
        : 'Cannot reach the KONE ELEVATE backend. Check that the API is running on port 8000.',
      { code: timedOut ? 'timeout' : 'network_error', offline: !timedOut },
    );
  }

  const { status, data } = error.response;

  // FastAPI validation errors (our custom handler).
  if (status === 422 && data?.issues) {
    const summary = data.issues
      .slice(0, 3)
      .map((issue) => `${issue.field || 'payload'}: ${issue.message}`)
      .join('; ');
    return new ApiError(`Validation failed - ${summary}`, {
      status,
      code: 'validation_error',
      details: data.issues,
    });
  }

  // Default FastAPI validation shape (list of errors under `detail`).
  if (status === 422 && Array.isArray(data?.detail)) {
    const summary = data.detail
      .slice(0, 3)
      .map((issue) => `${(issue.loc || []).slice(-1)[0]}: ${issue.msg}`)
      .join('; ');
    return new ApiError(`Validation failed - ${summary}`, {
      status,
      code: 'validation_error',
      details: data.detail,
    });
  }

  const messages = {
    400: 'The request was rejected as invalid.',
    401: 'You are not authorised to perform this action.',
    403: 'You do not have permission to perform this action.',
    404: 'The requested record was not found.',
    409: 'This action conflicts with the current state of the record.',
    429: 'Too many requests. Wait a moment and try again.',
    500: 'The server hit an unexpected error. The incident has been logged.',
    501: 'This capability is not implemented in the prototype.',
    502: 'The server could not reach a service it depends on. Please try again shortly.',
    503: 'The service is temporarily unavailable. Please try again shortly.',
  };

  const message =
    (typeof data?.detail === 'string' && data.detail) ||
    data?.message ||
    messages[status] ||
    `Request failed with status ${status}.`;

  return new ApiError(message, { status, code: data?.error || `http_${status}`, details: data });
}

/** Fired when a stored token is rejected, so AuthContext can sign the user out. */
export const UNAUTHORIZED_EVENT = 'kone-elevate:unauthorized';

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    // A 401 on a request we attached a token to means that token is no longer
    // good (expired, or the account was deactivated). Drop it and let the app
    // fall back to the sign-in screen. A 401 from the login endpoint itself is
    // just a failed sign-in attempt, not an expired session.
    const isLoginAttempt = error.config?.url?.includes('/auth/login');
    if (error.response?.status === 401 && !isLoginAttempt && tokenStore.get()) {
      tokenStore.clear();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }

    // Opt-in offline queueing (see offlineWrite below) - only for requests
    // that explicitly marked themselves queueable, and only on a genuine
    // network failure (no response at all), never on a real server-side
    // rejection like 409/422/403, which the technician needs to see and
    // act on immediately, not have silently queued.
    const queueSpec = error.config?.offlineQueue;
    if (!error.response && queueSpec) {
      const entry = await enqueue(queueSpec);
      return { data: { __queued: true, outboxId: entry.id }, status: 202 };
    }

    return Promise.reject(normaliseError(error));
  },
);

const unwrap = (promise) => promise.then((response) => response.data);

/**
 * Attach offline-queue replay instructions to an axios request config. Only
 * used on the handful of write paths a technician plausibly performs with
 * no signal (see the `offlineQueue:` calls below) - not applied blanket
 * to every mutation, because queueing e.g. a sign-in attempt makes no sense.
 */
function withOfflineQueue(config, { method, url, data = null, params = null, description }) {
  return { ...config, offlineQueue: { method, url, data, params, description } };
}

/* -------------------------------------------------------------------------- */
/* Authentication                                                              */
/* -------------------------------------------------------------------------- */
export const authApi = {
  /** Sign in. The backend expects an OAuth2 password form, not JSON. */
  login: (email, password) => {
    const form = new URLSearchParams();
    form.append('username', email);
    form.append('password', password);
    return unwrap(
      http.post('/auth/login', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }),
    );
  },
  me: () => unwrap(http.get('/auth/me')),

  /** Create an account. Note there is no role field - see the API docs. */
  signup: (payload) => unwrap(http.post('/auth/signup', payload)),
  verifyEmail: (email, code) => unwrap(http.post('/auth/signup/verify', { email, code })),
  resendCode: (email) => unwrap(http.post('/auth/signup/resend', { email })),
  signupPolicy: () => unwrap(http.get('/auth/signup/policy')),
};

/* -------------------------------------------------------------------------- */
/* Platform                                                                    */
/* -------------------------------------------------------------------------- */
export const platformApi = {
  health: () => unwrap(http.get('/health')),
  enums: () => unwrap(http.get('/meta/enums')),
};

/* -------------------------------------------------------------------------- */
/* Components                                                                  */
/* -------------------------------------------------------------------------- */
export const componentsApi = {
  list: (params = {}) => unwrap(http.get('/components', { params })),
  filters: () => unwrap(http.get('/components/filters')),
  get: (componentId) => unwrap(http.get(`/components/${encodeURIComponent(componentId)}`)),
  /** Offline-queueable: a technician registering a component with no signal is the point of P5. */
  create: (payload) =>
    unwrap(
      http.post(
        '/components',
        payload,
        withOfflineQueue(
          {},
          {
            method: 'post',
            url: '/components',
            data: payload,
            description: `Register component (${payload.component_type || 'unknown type'})`,
          },
        ),
      ),
    ),
  update: (componentId, payload) =>
    unwrap(http.put(`/components/${encodeURIComponent(componentId)}`, payload)),
  remove: (componentId) => unwrap(http.delete(`/components/${encodeURIComponent(componentId)}`)),

  serviceEvents: (componentId, params = {}) =>
    unwrap(http.get(`/components/${encodeURIComponent(componentId)}/service-events`, { params })),
  /** Offline-queueable: logging a service event is a core machine-room task. */
  addServiceEvent: (componentId, payload) => {
    const url = `/components/${encodeURIComponent(componentId)}/service-events`;
    return unwrap(
      http.post(
        url,
        payload,
        withOfflineQueue(
          {},
          {
            method: 'post',
            url,
            data: payload,
            description: `Add ${payload.event_type || 'service'} event for ${componentId}`,
          },
        ),
      ),
    );
  },

  /**
   * Offline-queueable, with an honest limit: this queues the *request* for
   * an assessment, to run once back online. It does not run the Random
   * Forest inside the browser - that would need shipping the model
   * (ONNX/WASM) to the client, which was not attempted in this pass. See
   * docs/offline-pwa.md for why "against a cached model" in the original
   * plan wording is only partly true here.
   */
  predict: (componentId, params = {}) => {
    const url = `/components/${encodeURIComponent(componentId)}/predict`;
    return unwrap(
      http.post(
        url,
        null,
        withOfflineQueue(
          { params },
          {
            method: 'post',
            url,
            params,
            description: `Run AI assessment for ${componentId}`,
          },
        ),
      ),
    );
  },
  predictions: (componentId, params = {}) =>
    unwrap(http.get(`/components/${encodeURIComponent(componentId)}/predictions`, { params })),

  exportCsv: () => http.get('/components/export', { responseType: 'blob' }).then((r) => r.data),
};

/* -------------------------------------------------------------------------- */
/* Prediction / model                                                          */
/* -------------------------------------------------------------------------- */
export const predictionApi = {
  predict: (payload, params = {}) => unwrap(http.post('/predict', payload, { params })),
  batch: (payloads) => unwrap(http.post('/predict/batch', payloads)),
  modelInfo: () => unwrap(http.get('/model/info')),
  modelMetrics: () => unwrap(http.get('/model/metrics')),
  featureImportance: () => unwrap(http.get('/model/feature-importance')),
  calibration: () => unwrap(http.get('/model/calibration')),
  reloadModel: () => unwrap(http.post('/model/reload')),
  recent: (limit = 10) => unwrap(http.get('/predictions/recent', { params: { limit } })),
  exportCsv: () => http.get('/predictions/export', { responseType: 'blob' }).then((r) => r.data),
};

/* -------------------------------------------------------------------------- */
/* Passports                                                                   */
/* -------------------------------------------------------------------------- */
export const passportApi = {
  get: (componentId) => unwrap(http.get(`/passports/${encodeURIComponent(componentId)}`)),
  qrInfo: (componentId) => unwrap(http.get(`/passports/${encodeURIComponent(componentId)}/qr/info`)),
  qrImageUrl: (componentId, boxSize = 10) =>
    `${API_BASE_URL}/passports/${encodeURIComponent(componentId)}/qr?box_size=${boxSize}`,
  qrDownloadUrl: (componentId) =>
    `${API_BASE_URL}/passports/${encodeURIComponent(componentId)}/qr?download=true&box_size=14`,
  resolve: (value) => unwrap(http.get('/passports/lookup/resolve', { params: { value } })),
  report: (componentId) => unwrap(http.get(`/passports/${encodeURIComponent(componentId)}/report`)),
  life: (componentId) => unwrap(http.get(`/passports/${encodeURIComponent(componentId)}/life`)),
};

/* -------------------------------------------------------------------------- */
/* Dashboard / analytics                                                       */
/* -------------------------------------------------------------------------- */
export const dashboardApi = {
  summary: (params = {}) => unwrap(http.get('/dashboard/summary', { params })),
  disposition: () => unwrap(http.get('/dashboard/disposition')),
  healthDistribution: () => unwrap(http.get('/dashboard/health-distribution')),
  componentTypes: () => unwrap(http.get('/dashboard/component-types')),
  lifecycle: () => unwrap(http.get('/dashboard/lifecycle')),
  confidence: () => unwrap(http.get('/dashboard/confidence')),
  monthlyActivity: (months = 12) =>
    unwrap(http.get('/dashboard/monthly-activity', { params: { months } })),
  recoveryValue: () => unwrap(http.get('/dashboard/recovery-value')),
  impact: () => unwrap(http.get('/dashboard/impact')),
  safetyQueue: (limit = 50) => unwrap(http.get('/dashboard/safety-queue', { params: { limit } })),
  analytics: (params = {}) => unwrap(http.get('/dashboard/analytics', { params })),
};

/* -------------------------------------------------------------------------- */
/* Forecast (end-of-life + component-recovery capacity)                       */
/* -------------------------------------------------------------------------- */
export const forecastApi = {
  eol: (params = {}) => unwrap(http.get('/forecast/eol', { params })),
  capacity: (params = {}) => unwrap(http.get('/forecast/capacity', { params })),
  model: (full = false) => unwrap(http.get('/forecast/model', { params: { full } })),
  siteImpact: (params = {}) => unwrap(http.get('/forecast/site-impact', { params })),
};

/* -------------------------------------------------------------------------- */
/* Compliance (ESRS E5, BRSR, material-flow ledger, standards, anchoring)      */
/* -------------------------------------------------------------------------- */
export const complianceApi = {
  esrsE5: (period) => unwrap(http.get('/reports/esrs-e5', { params: { period } })),
  brsr: (period) => unwrap(http.get('/reports/brsr', { params: { period } })),
  materialFlow: (params = {}) => unwrap(http.get('/reports/material-flow', { params })),
  ledgerSummary: () => unwrap(http.get('/reports/ledger-summary')),
  circularity: (params = {}) => unwrap(http.get('/reports/circularity', { params })),
  standards: (componentType) =>
    unwrap(http.get('/reports/standards', { params: { component_type: componentType } })),
  anchors: (limit = 30) => unwrap(http.get('/reports/anchors', { params: { limit } })),
  exportEsrsCsv: (period) =>
    http.get('/reports/esrs-e5.csv', { params: { period }, responseType: 'blob' }).then((r) => r.data),
};

/* -------------------------------------------------------------------------- */
/* Audit                                                                       */
/* -------------------------------------------------------------------------- */
export const auditApi = {
  list: (params = {}) => unwrap(http.get('/audit', { params })),
  verify: () => unwrap(http.get('/audit/verify')),
  stats: () => unwrap(http.get('/audit/stats')),
  forEntity: (entityType, entityId) =>
    unwrap(http.get(`/audit/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`)),
  exportCsv: () => http.get('/audit/export', { responseType: 'blob' }).then((r) => r.data),
};

/* -------------------------------------------------------------------------- */
/* Simulation                                                                 */
/* -------------------------------------------------------------------------- */
export const simulationApi = {
  reference: () => unwrap(http.get('/simulation/reference')),
  advance: (state, loadKg, months) =>
    unwrap(http.post('/simulation/advance', { state, load_kg: loadKg, months })),
  startFrom: (componentId) =>
    unwrap(http.post(`/simulation/start/${encodeURIComponent(componentId)}`)),
  saveScenario: (componentId, state, name) =>
    unwrap(http.post(`/simulation/scenarios/${encodeURIComponent(componentId)}`, { state, name })),
  scenarios: (componentId) =>
    unwrap(http.get(`/simulation/scenarios/${encodeURIComponent(componentId)}`)),
  deleteScenario: (scenarioId) => unwrap(http.delete(`/simulation/scenarios/item/${scenarioId}`)),
};

/* -------------------------------------------------------------------------- */
/* Field data: measured inspections and sensor telemetry                      */
/* -------------------------------------------------------------------------- */
export const fieldDataApi = {
  checklists: () => unwrap(http.get('/inspections/checklists')),
  preview: (componentType, measurements) =>
    unwrap(http.post('/inspections/preview', { component_type: componentType, measurements })),
  recordInspection: (componentId, payload) =>
    unwrap(http.post(`/components/${encodeURIComponent(componentId)}/inspections`, payload)),
  telemetry: (componentId) =>
    unwrap(http.get(`/components/${encodeURIComponent(componentId)}/telemetry`)),
  uploadCsv: (componentId, file, source, ratedLoadKg) => {
    const form = new FormData();
    form.append('file', file);
    form.append('source', source);
    form.append('rated_load_kg', String(ratedLoadKg));
    // The instance defaults to JSON, which would make axios serialise the form;
    // multipart lets the browser set the boundary itself.
    return unwrap(
      http.post(`/components/${encodeURIComponent(componentId)}/telemetry/csv`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      }),
    );
  },
};

export default http;
