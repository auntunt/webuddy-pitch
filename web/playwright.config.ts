import { defineConfig } from '@playwright/test'

const PORT = process.env.NEXT_E2E_PORT || '8891'
const TOKEN = process.env.NEXT_E2E_TOKEN || 'e2e-next-token'

export default defineConfig({
  testDir: './tests',
  testMatch: 'next.spec.ts',
  timeout: 120_000,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  expect: { timeout: 30_000 },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 900 },
    screenshot: 'off',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: `${process.env.NEXT_E2E_PYTHON || 'python3'} ../tests/e2e/next_server.py`,
    url: `http://127.0.0.1:${PORT}/login`,
    reuseExistingServer: false,
    timeout: 300_000,
    env: { NEXT_E2E_PORT: PORT, NEXT_E2E_TOKEN: TOKEN },
  },
})
