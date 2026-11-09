import { createHash } from 'node:crypto'
import { mkdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
import { test, expect, type Page } from '@playwright/test'

const fixture = JSON.parse(readFileSync(join(HERE, '../../tests/e2e/.runtime/fixture.json'), 'utf8'))
const PASSWORD = 'e2e-pass-123'
const SHOTS = '/tmp/wb-shots'

mkdirSync(SHOTS, { recursive: true })

test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.locator('input[name=username]').fill(fixture.user)
  await page.locator('input[name=password]').fill(PASSWORD)
  await page.getByRole('button', { name: '登录' }).click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 })
  await page.goto('/next/')
  await expect(page.locator('.topbar .brand')).toBeVisible()
})

async function shot(page: Page, name: string) {
  await page.screenshot({ path: join(SHOTS, `next-${test.info().project.name}-${name}.png`), fullPage: false })
}

test('shell loads with brand, project and navigation', async ({ page }) => {
  await expect(page.locator('.topbar .brand')).toContainText('E2E Webuddy')
  await expect(page.locator('.project-picker select')).toHaveValue('E2E')
  await expect(page.locator('.sidenav, .bottomnav').first()).toContainText('验证现有改动')
  await shot(page, 'shell')
})

test('resolve then submit lands on the candidate page', async ({ page }) => {
  await page.goto(`/next/p/E2E/verify?ticket=${fixture.ticket}`)
  await expect(page.locator('.field select')).toHaveValue(fixture.ticket)
  await page.locator('.grid2 input').first().fill(fixture.base)
  await page.locator('.grid2 input').nth(1).fill(fixture.doc)
  await page.locator('.field textarea').fill('doc-only candidate from e2e')
  await page.getByRole('button', { name: '解析提交编号' }).click()
  await expect(page.locator('.resolved')).toContainText('基线')
  await expect(page.locator('.resolved')).toContainText('候选')
  await shot(page, 'verify-resolved')
  await page.getByRole('button', { name: '验证现有改动' }).click()
  await page.waitForURL(/\/next\/p\/E2E\/candidates\/\d+/, { timeout: 30000 })
  await expect(page.locator('h1')).toContainText('候选 #')
  await shot(page, 'candidate-after-submit')
})

test('candidate page shows the gate block for the assertion-deleting candidate', async ({ page }) => {
  await page.goto(`/next/p/E2E/candidates/${fixture.ids.tampered}`)
  await expect(page.locator('h1')).toContainText(`候选 #${fixture.ids.tampered}`)
  await expect(page.getByRole('heading', { name: '门禁相关变更' })).toBeVisible()
  await expect(page.locator('.gate-list')).toContainText('tests/test_flow.py')
  await shot(page, 'candidate-gate')
})

test('report export downloads with verified sha256', async ({ page }) => {
  const cid = fixture.ids.good
  const manifest = await page.evaluate(async ({ ticket, cid }) => {
    const r = await fetch('/api/team', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-TMH': '1' },
      body: JSON.stringify({ ticket, action: 'candidate_report_create', candidate_id: cid, request_id: `pw-${Date.now()}` }),
    })
    const j = await r.json()
    if (!r.ok) throw new Error(j.error || String(r.status))
    return j.result || j
  }, { ticket: fixture.ticket, cid })
  const entry = (manifest.files || []).find((f: { name: string }) => f.name === 'report.md')
  expect(entry, 'manifest has report.md').toBeTruthy()

  await page.goto(`/next/p/E2E/candidates/${cid}`)
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 60000 }),
    page.getByRole('button', { name: '导出验证报告' }).click(),
  ])
  const path = await download.path()
  const bytes = readFileSync(path)
  const sha = createHash('sha256').update(bytes).digest('hex')
  expect(sha).toBe(entry.sha256)
  expect(bytes.length).toBe(entry.bytes)
  await shot(page, 'candidate-report')
})

test('unauthenticated /next/ is rejected', async ({ browser }) => {
  const context = await browser.newContext()
  const response = await context.request.get('/next/p/E2E/verify', { maxRedirects: 0 })
  expect(response.status()).toBe(303)
  expect(response.headers()['location']).toContain('/login')
  await context.close()
})
