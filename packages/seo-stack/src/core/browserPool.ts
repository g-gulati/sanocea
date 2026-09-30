/**
 * SANOCEA SEO Stack — Headless Browser Pool & SPA Escalation Engine
 * 
 * Provides built-in, autonomous Chromium rendering for Single-Page Applications
 * (React, Vite, Next.js, Vue, Angular) without requiring external script wrappers.
 */

import * as fs from 'fs';
import { chromium, Browser, BrowserContext } from 'playwright';

const SYSTEM_CHROME_PATHS = [
  process.env.CHROME_BIN,
  process.env.CHROMIUM_PATH,
  '/snap/bin/chromium',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable'
].filter((p): p is string => Boolean(p && fs.existsSync(p)));

export interface BrowserRenderResult {
  renderedHtml: string;
  executionTimeMs: number;
}

export class BrowserPool {
  private static instance: BrowserPool | null = null;
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private isInitializing = false;

  private constructor() {}

  public static getInstance(): BrowserPool {
    if (!BrowserPool.instance) {
      BrowserPool.instance = new BrowserPool();
    }
    return BrowserPool.instance;
  }

  /**
   * Initializes or returns the cached headless Chromium browser
   */
  public async getBrowser(): Promise<Browser> {
    if (this.browser && this.browser.isConnected()) {
      return this.browser;
    }

    if (this.isInitializing) {
      while (this.isInitializing) {
        await new Promise(r => setTimeout(r, 50));
      }
      if (this.browser && this.browser.isConnected()) {
        return this.browser;
      }
    }

    this.isInitializing = true;
    try {
      const launchOptions: any = {
        headless: true,
        args: [
          '--no-sandbox',
          '--disable-setuid-sandbox',
          '--disable-dev-shm-usage',
          '--disable-accelerated-2d-canvas',
          '--no-first-run',
          '--no-zygote',
          '--disable-gpu'
        ]
      };

      if (SYSTEM_CHROME_PATHS.length > 0) {
        launchOptions.executablePath = SYSTEM_CHROME_PATHS[0];
      }

      try {
        this.browser = await chromium.launch(launchOptions);
      } catch (err: any) {
        // Fallback: try launching default bundled chromium if custom path fails
        if (launchOptions.executablePath) {
          delete launchOptions.executablePath;
          this.browser = await chromium.launch(launchOptions);
        } else {
          throw err;
        }
      }

      return this.browser;
    } finally {
      this.isInitializing = false;
    }
  }

  /**
   * Renders a live URL with JavaScript execution and waits for DOM hydration
   */
  public async renderUrl(url: string, waitTimeoutMs = 8000): Promise<BrowserRenderResult> {
    const startTime = Date.now();
    const browser = await this.getBrowser();
    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (compatible; SanoceaSeoBot/1.0; +https://www.sanocea.com/bot)',
      viewport: { width: 1440, height: 900 }
    });

    const page = await context.newPage();

    try {
      // Abort non-essential media to accelerate crawl throughput 5-10x
      await page.route('**/*', (route) => {
        const type = route.request().resourceType();
        if (['image', 'media', 'font'].includes(type)) {
          return route.abort();
        }
        return route.continue();
      });

      await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: waitTimeoutMs
      });

      // Wait briefly for client-side JS hydration (root mounting, heading injection)
      try {
        await page.waitForLoadState('networkidle', { timeout: 2500 });
      } catch {
        // Networkidle timeout is non-fatal; continue with rendered DOM
      }

      const renderedHtml = await page.content();
      return {
        renderedHtml,
        executionTimeMs: Date.now() - startTime
      };
    } finally {
      await page.close().catch(() => {});
      await context.close().catch(() => {});
    }
  }

  /**
   * Renders static HTML content inside the browser to simulate client-side hydration
   */
  public async renderContent(html: string, baseUrl = 'https://sanocea.internal', waitTimeoutMs = 5000): Promise<BrowserRenderResult> {
    const startTime = Date.now();
    const browser = await this.getBrowser();
    const context = await browser.newContext({
      userAgent: 'Mozilla/5.0 (compatible; SanoceaSeoBot/1.0; +https://www.sanocea.com/bot)'
    });
    const page = await context.newPage();

    try {
      await page.setContent(html, {
        waitUntil: 'domcontentloaded',
        timeout: waitTimeoutMs
      });

      try {
        await page.waitForLoadState('networkidle', { timeout: 1500 });
      } catch {
        // non-fatal
      }

      const renderedHtml = await page.content();
      return {
        renderedHtml,
        executionTimeMs: Date.now() - startTime
      };
    } finally {
      await page.close().catch(() => {});
      await context.close().catch(() => {});
    }
  }

  /**
   * Graceful shutdown of browser processes
   */
  public async close(): Promise<void> {
    if (this.context) {
      await this.context.close().catch(() => {});
      this.context = null;
    }
    if (this.browser) {
      await this.browser.close().catch(() => {});
      this.browser = null;
    }
  }
}
