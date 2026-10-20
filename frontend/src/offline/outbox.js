/**
 * The offline write queue: assessments, service events and removals
 * recorded with no network, replayed once one exists again.
 *
 * Conflict model, stated plainly
 * -------------------------------
 * This system's writes are overwhelmingly *appends* - register a
 * component, log a service event, list a recovered part, run an
 * assessment. "Last write wins" is not a meaningful conflict strategy for
 * an append; there is nothing to overwrite. The one real conflict shape -
 * a duplicate serial number entered twice while offline, or a recovery
 * match someone else already accepted before this device reconnected -
 * surfaces as the backend's own 409/422 response. `syncOutbox` marks that
 * entry `failed` with the server's own reason and stops there: it is never
 * silently discarded, never silently retried, and never applied twice.
 * That is what "conflict-safe" means for an append-only write path - it is
 * a different (and, for this domain, more honest) guarantee than merging
 * two conflicting edits, which this system's write shapes do not actually
 * produce.
 */

import { getDb, OUTBOX_STORE } from './db';

const CHANGE_EVENT = 'ke-offline:outbox-changed';

function notifyChange() {
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Subscribe to outbox changes. Returns an unsubscribe function. */
export function onOutboxChange(callback) {
  window.addEventListener(CHANGE_EVENT, callback);
  return () => window.removeEventListener(CHANGE_EVENT, callback);
}

function newId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Queue one write. `replay` is the exact axios request shape needed to
 * perform it later - passed explicitly by the caller rather than
 * introspected from the failed request, since axios mutates `config.data`
 * into a serialised string internally and relying on that is fragile.
 */
export async function enqueue({ method, url, data = null, params = null, description }) {
  const db = await getDb();
  const entry = {
    id: newId(),
    method,
    url,
    data,
    params,
    description: description || `${String(method).toUpperCase()} ${url}`,
    status: 'pending',
    error: null,
    createdAt: new Date().toISOString(),
  };
  await db.put(OUTBOX_STORE, entry);
  notifyChange();
  return entry;
}

export async function listOutbox() {
  const db = await getDb();
  const all = await db.getAll(OUTBOX_STORE);
  return all.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function pendingCount() {
  const all = await listOutbox();
  return all.filter((entry) => entry.status === 'pending').length;
}

export async function removeEntry(id) {
  const db = await getDb();
  await db.delete(OUTBOX_STORE, id);
  notifyChange();
}

/** A failed entry needs a human decision before it is worth retrying. */
export async function retryEntry(id) {
  const db = await getDb();
  const entry = await db.get(OUTBOX_STORE, id);
  if (!entry) return;
  entry.status = 'pending';
  entry.error = null;
  await db.put(OUTBOX_STORE, entry);
  notifyChange();
}

/**
 * Replay every pending entry, oldest first, against the raw network client
 * - never against the queueing wrapper itself, or a still-failing entry
 * would just re-queue instead of surfacing as failed.
 */
export async function syncOutbox(rawHttpClient) {
  const db = await getDb();
  const entries = (await listOutbox()).filter((entry) => entry.status === 'pending');
  const result = { synced: [], failed: [] };

  for (const entry of entries) {
    try {
      await rawHttpClient.request({
        method: entry.method,
        url: entry.url,
        data: entry.data,
        params: entry.params,
      });
      await db.delete(OUTBOX_STORE, entry.id);
      result.synced.push(entry);
    } catch (error) {
      if (!error.response) {
        // Still offline, or the backend is unreachable - stop here and
        // leave the rest pending rather than burning through every entry
        // against a network that plainly is not there.
        break;
      }
      entry.status = 'failed';
      entry.error =
        (typeof error.response.data?.detail === 'string' && error.response.data.detail) ||
        `Server rejected this change (HTTP ${error.response.status}).`;
      await db.put(OUTBOX_STORE, entry);
      result.failed.push(entry);
    }
  }

  notifyChange();
  return result;
}
