import { defineConfig } from '@playwright/test'
import { fileURLToPath } from 'node:url'
process.env.PLAYWRIGHT_BROWSERS_PATH = fileURLToPath(new URL('./node_modules/.cache/playwright', import.meta.url))
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1, timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:4173', viewport: { width: 1440, height: 1000 },
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] },
    screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 4173 --strictPort', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
})
