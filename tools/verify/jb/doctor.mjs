import { chromium } from '@playwright/test';
import { login } from './tmh-helpers.mjs';
const base = process.argv[2], out = process.argv[3];
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1440, height: 900 } });
const errs = []; page.on('pageerror', (e) => errs.push(String(e)));
await page.goto(base + 'user/login'); await page.locator('form input').first().waitFor({ timeout: 240000 }).catch(() => {}); await page.waitForTimeout(1000);
await page.screenshot({ path: out + '/login.png' });
console.log('inputs', JSON.stringify(await page.locator('form input:visible').evaluateAll((a) => a.map((i) => i.placeholder))));
try { await login(page, base); await page.waitForTimeout(4000); console.log('LOGIN_OK', page.url()); }
catch (e) { console.log('LOGIN_FAIL', String(e).slice(0, 300)); }
await page.screenshot({ path: out + '/after.png' });
console.log('pageerrors', errs.length);
await b.close();
