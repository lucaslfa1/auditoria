/** Outcome of a single item processed by {@link runWithConcurrency}. */
export interface SettledResult<T, R> {
    item: T;
    ok: boolean;
    value?: R;
    error?: unknown;
}

/**
 * Run `worker` over `items` with at most `limit` promises in flight at once.
 *
 * Errors are isolated per item (the worker is wrapped in try/catch), so a single
 * failure never aborts the others — every item gets a {@link SettledResult}, in
 * input order. Used by the triage queue to classify several recordings at once
 * while honoring a small concurrency cap (Azure rate limits).
 */
export async function runWithConcurrency<T, R>(
    items: readonly T[],
    limit: number,
    worker: (item: T) => Promise<R>,
): Promise<Array<SettledResult<T, R>>> {
    const results: Array<SettledResult<T, R>> = new Array(items.length);
    if (items.length === 0) return results;

    const effectiveLimit = Math.max(1, Math.min(Math.floor(limit) || 1, items.length));
    let next = 0;

    async function runner(): Promise<void> {
        while (true) {
            const index = next++;
            if (index >= items.length) return;
            const item = items[index];
            try {
                results[index] = { item, ok: true, value: await worker(item) };
            } catch (error) {
                results[index] = { item, ok: false, error };
            }
        }
    }

    await Promise.all(Array.from({ length: effectiveLimit }, () => runner()));
    return results;
}
