/**
 * The offline write queue (src/offline/outbox.js). This is the piece P5's
 * "conflict-safe sync on reconnect, with a visible pending-sync state"
 * deliverable actually rests on, so it gets real IndexedDB-backed tests
 * (via fake-indexeddb - see src/test/setup.js) rather than being trusted
 * on inspection alone.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import 'fake-indexeddb/auto';
import { IDBFactory } from 'fake-indexeddb';
import { _resetDbForTests } from '../offline/db';
import {
  enqueue,
  listOutbox,
  onOutboxChange,
  pendingCount,
  removeEntry,
  retryEntry,
  syncOutbox,
} from '../offline/outbox';

beforeEach(() => {
  // A fresh database per test: swap in a clean fake IndexedDB backend AND
  // drop outbox.js's cached connection, which otherwise keeps pointing at
  // whichever backend was live the first time getDb() ran.
  globalThis.indexedDB = new IDBFactory();
  _resetDbForTests();
});

describe('enqueue / listOutbox', () => {
  it('stores a queued write with a pending status', async () => {
    const entry = await enqueue({
      method: 'post',
      url: '/components',
      data: { component_type: 'Motor' },
      description: 'Register component (Motor)',
    });

    expect(entry.status).toBe('pending');
    expect(entry.id).toBeTruthy();

    const all = await listOutbox();
    expect(all).toHaveLength(1);
    expect(all[0].description).toBe('Register component (Motor)');
  });

  it('orders entries oldest first', async () => {
    const first = await enqueue({ method: 'post', url: '/a', description: 'first' });
    await new Promise((resolve) => setTimeout(resolve, 2));
    const second = await enqueue({ method: 'post', url: '/b', description: 'second' });

    const all = await listOutbox();
    expect(all.map((e) => e.id)).toEqual([first.id, second.id]);
  });

  it('reports a pending count', async () => {
    await enqueue({ method: 'post', url: '/a', description: 'a' });
    await enqueue({ method: 'post', url: '/b', description: 'b' });
    expect(await pendingCount()).toBe(2);
  });

  it('notifies subscribers on change', async () => {
    const handler = vi.fn();
    const unsubscribe = onOutboxChange(handler);
    await enqueue({ method: 'post', url: '/a', description: 'a' });
    expect(handler).toHaveBeenCalledTimes(1);
    unsubscribe();
    await enqueue({ method: 'post', url: '/b', description: 'b' });
    expect(handler).toHaveBeenCalledTimes(1);
  });
});

describe('syncOutbox', () => {
  it('replays pending entries against the real client and removes them on success', async () => {
    await enqueue({ method: 'post', url: '/components', data: { a: 1 }, description: 'one' });
    await enqueue({ method: 'post', url: '/components', data: { a: 2 }, description: 'two' });

    const request = vi.fn().mockResolvedValue({ data: {} });
    const result = await syncOutbox({ request });

    expect(request).toHaveBeenCalledTimes(2);
    expect(result.synced).toHaveLength(2);
    expect(await listOutbox()).toHaveLength(0);
  });

  it('marks a server-rejected entry as failed instead of discarding or looping it', async () => {
    await enqueue({ method: 'post', url: '/components', data: { serial_number: 'dup' }, description: 'dup' });

    const request = vi.fn().mockRejectedValue({
      response: { status: 409, data: { detail: "Serial number 'dup' is already registered." } },
    });
    const result = await syncOutbox({ request });

    expect(result.failed).toHaveLength(1);
    const [entry] = await listOutbox();
    expect(entry.status).toBe('failed');
    expect(entry.error).toContain('already registered');
  });

  it('stops replaying (without discarding) the moment the network is still down', async () => {
    await enqueue({ method: 'post', url: '/a', description: 'a' });
    await enqueue({ method: 'post', url: '/b', description: 'b' });

    const request = vi.fn().mockRejectedValue({ response: undefined }); // network error, no response at all
    const result = await syncOutbox({ request });

    expect(result.synced).toHaveLength(0);
    expect(result.failed).toHaveLength(0);
    expect(await pendingCount()).toBe(2); // both still queued, neither lost
  });

  it('never re-syncs an entry already marked failed without an explicit retry', async () => {
    await enqueue({ method: 'post', url: '/a', description: 'a' });
    const rejecting = vi.fn().mockRejectedValue({ response: { status: 422, data: {} } });
    await syncOutbox({ request: rejecting });

    const succeeding = vi.fn().mockResolvedValue({ data: {} });
    await syncOutbox({ request: succeeding });
    expect(succeeding).not.toHaveBeenCalled();

    const [entry] = await listOutbox();
    await retryEntry(entry.id);
    await syncOutbox({ request: succeeding });
    expect(succeeding).toHaveBeenCalledTimes(1);
  });
});

describe('removeEntry', () => {
  it('discards a queued or failed entry permanently', async () => {
    const entry = await enqueue({ method: 'post', url: '/a', description: 'a' });
    await removeEntry(entry.id);
    expect(await listOutbox()).toHaveLength(0);
  });
});
