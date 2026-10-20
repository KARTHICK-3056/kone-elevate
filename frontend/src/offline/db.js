/**
 * IndexedDB handle for the offline write queue.
 *
 * One database, one object store: `outbox`. Reads (passport lookups,
 * component list/detail) do not need a hand-rolled cache at all - the
 * service worker's Workbox runtime caching (see vite.config.js) already
 * intercepts every same-origin request, axios's XHR calls included, and
 * serves the last-seen response when the network is not there. Only
 * *writes* need explicit handling, because a write cannot simply be
 * "served from cache" - it has to be replayed later. See outbox.js.
 */

import { openDB } from 'idb';

const DB_NAME = 'ke-offline';
const DB_VERSION = 1;
export const OUTBOX_STORE = 'outbox';

let dbPromise = null;

export function getDb() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(OUTBOX_STORE)) {
          const store = db.createObjectStore(OUTBOX_STORE, { keyPath: 'id' });
          store.createIndex('status', 'status');
          store.createIndex('createdAt', 'createdAt');
        }
      },
    });
  }
  return dbPromise;
}

/** Test-only: drop the cached connection so the next getDb() reopens fresh. */
export function _resetDbForTests() {
  dbPromise = null;
}
