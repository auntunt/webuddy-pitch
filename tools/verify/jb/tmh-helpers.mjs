import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';

const md5 = (s) => crypto.createHash('md5').update(s, 'utf8').digest('hex');

function secret() {
  const yml = fs.readFileSync(process.env.TMH_JB_YML, 'utf8');
  const m = yml.match(/signatureSecret:\s*(\S+)/);
  return m ? m[1] : '';
}

export function captchaFor(checkKey) {
  const s = secret();
  const keys = execFileSync('redis-cli', ['--scan'], { encoding: 'utf8' }).split('\n').filter((k) => /^[0-9a-f]{32}$/.test(k));
  for (const k of keys) {
    const v = execFileSync('redis-cli', ['--raw', 'GET', k], { encoding: 'utf8' }).trim().replace(/^"|"$/g, '');
    if (v.length === 4 && md5(v + checkKey + s) === k) return v;
  }
  return '';
}

export async function login(page, base, user = 'admin', pass = '123456') {
  let checkKey = '';
  page.on('request', (r) => { const m = r.url().match(/randomImage\/([^/?]+)/); if (m) checkKey = m[1]; });
  await page.goto(base + 'user/login');
  await page.locator('form input').first().waitFor({ timeout: 240000 });
  for (let i = 0; i < 60 && !checkKey; i++) await page.waitForTimeout(500);
  await page.waitForTimeout(2000);
  const code = captchaFor(checkKey);
  if (!code) throw new Error('captcha not found for ' + checkKey);
  const inputs = page.locator('form input:visible');
  await inputs.nth(0).fill(user);
  await inputs.nth(1).fill(pass);
  await inputs.nth(2).fill(code);
  await page.getByRole('button', { name: /登\s*录/ }).first().click();
  await page.waitForURL((u) => !u.pathname.endsWith('/user/login'), { timeout: 60000 });
}
