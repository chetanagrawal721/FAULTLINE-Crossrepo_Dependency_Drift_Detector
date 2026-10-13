import { useCallback, useEffect, useRef, useState } from "react";

export type Async<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/**
 * Load something from the API. When the inputs change the previous data is cleared; a refresh of the same record (polling, reload) keeps it on screen. `pollMs` with `keepPolling` re-loads until the data says it is finished (a running job, a repository still
 * being fetched). A failed load keeps the previous data on screen and reports the error; it never turns into an empty result.
 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[], opts: { pollMs?: number; keepPolling?: (data: T) => boolean } = {}): Async<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const timer = useRef<number | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const keyRef = useRef<string | null>(null);
  useEffect(() => {
    let alive = true;
    const key = JSON.stringify(deps);
    if (keyRef.current !== null && keyRef.current !== key) {
      setData(null); // a different record is being asked for: never show the previous one in its place
      setError(null);
    }
    keyRef.current = key;
    setLoading(true);
    loadRef
      .current()
      .then((v) => {
        if (!alive) return;
        setData(v);
        setError(null);
        if (opts.pollMs && opts.keepPolling?.(v)) timer.current = window.setTimeout(() => setTick((n) => n + 1), opts.pollMs);
      })
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}

export const short = (sha: string | null | undefined, n = 10) => (sha ? sha.slice(0, n) : "—");

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "n/a";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60000)} min ${Math.round((ms % 60000) / 1000)} s`;
}

export const words = (s: string) => s.replaceAll("_", " ");
