/**
 * Tracks connectivity and the offline write queue, and replays the queue
 * automatically the moment the browser reports it is back online.
 */

import { useCallback, useEffect, useState } from 'react';
import http from '../api/client';
import { listOutbox, onOutboxChange, syncOutbox } from '../offline/outbox';

export function useOfflineSync() {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [outbox, setOutbox] = useState([]);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(async () => {
    setOutbox(await listOutbox());
  }, []);

  const sync = useCallback(async () => {
    if (!navigator.onLine || syncing) return;
    setSyncing(true);
    try {
      await syncOutbox(http);
    } finally {
      setSyncing(false);
      await refresh();
    }
  }, [refresh, syncing]);

  useEffect(() => {
    refresh();
    const unsubscribe = onOutboxChange(refresh);

    const handleOnline = () => {
      setIsOnline(true);
      sync();
    };
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // A tab that was already open when connectivity returned, or that never
    // fired a browser 'online' event reliably (some mobile browsers are
    // inconsistent about it), still gets a chance to flush the queue.
    if (navigator.onLine) sync();

    return () => {
      unsubscribe();
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pending = outbox.filter((entry) => entry.status === 'pending');
  const failed = outbox.filter((entry) => entry.status === 'failed');

  return {
    isOnline,
    syncing,
    pendingCount: pending.length,
    failedCount: failed.length,
    outbox,
    syncNow: sync,
    refresh,
  };
}
