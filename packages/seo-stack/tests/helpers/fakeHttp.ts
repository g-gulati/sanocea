/** HTTP-level test double: a fetch() implementation driven by a route table. Test-only. */
export type FakeRoute =
  | { status: number; body?: string | Buffer; headers?: Record<string, string> }
  | { throw: Error }
  | { hang: true };

export function fakeFetch(routes: Record<string, FakeRoute | (() => FakeRoute)>): typeof fetch & { calls: Array<{ url: string; init?: RequestInit }> } {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const impl = (async (input: any, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.url ?? String(input);
    calls.push({ url, init });
    const entry = routes[url];
    if (!entry) return new Response('not found', { status: 404 });
    const r = typeof entry === 'function' ? entry() : entry;
    if ('throw' in r) throw r.throw;
    if ('hang' in r) {
      return new Promise((_, reject) => {
        // A real socket keeps the event loop alive; AbortSignal.timeout's timer is unref'd, so hold it open.
        const keepAlive = setTimeout(() => {}, 30000);
        init?.signal?.addEventListener('abort', () => { clearTimeout(keepAlive); reject(init.signal!.reason); });
      });
    }
    return new Response(r.body ?? '', { status: r.status, headers: r.headers });
  }) as any;
  impl.calls = calls;
  return impl;
}

export const urlset = (urls: string[]) =>
  `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.map(u => `<url><loc>${u}</loc></url>`).join('')}</urlset>`;

export const sitemapIndex = (locs: string[]) =>
  `<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${locs.map(u => `<sitemap><loc>${u}</loc></sitemap>`).join('')}</sitemapindex>`;
