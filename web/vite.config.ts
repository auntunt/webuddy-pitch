import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: './',
  plugins: [vue()],
  server: {
    open: '/next/',
    proxy: Object.fromEntries(['/api', '/login', '/logout', '/pv'].map(path => [path, {
      target: process.env.WEBUDDY_API_URL || 'http://127.0.0.1:8790',
    }])),
  },
  build: {
    outDir: '../tmh/platform/web_dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts', 'tests/**/*.test.ts'],
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
