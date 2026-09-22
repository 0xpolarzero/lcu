import { chromium } from '/fixture/release/runtime/lib/node_modules/playwright-core/index.mjs';
import { writeFile } from 'node:fs/promises';

// This profile exists only inside the disposable container. Its standard path
// matches the unchanged native-host installer's Chromium manifest destination.
const context = await chromium.launchPersistentContext('/root/.config/chromium', {
  headless: false,
  args: ['--disable-extensions-except=/fixture/extension', '--load-extension=/fixture/extension', '--no-sandbox'],
});
const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
if (!worker.url().startsWith('chrome-extension://hehggadaopoacecdllhhajmbjkdcmajg/')) {
  throw new Error('The pinned official extension was not loaded');
}
await writeFile('/tmp/lcu-browser-ready', worker.url());
process.on('SIGTERM', () => context.close().then(() => process.exit()));
await new Promise(() => {});
