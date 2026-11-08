import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
process.env.PLAYWRIGHT_BROWSERS_PATH = fileURLToPath(new URL('../node_modules/.cache/playwright', import.meta.url))
const cli = fileURLToPath(new URL('../node_modules/playwright/cli.js', import.meta.url))
const result = spawnSync(process.execPath, [cli, 'install', 'chromium'], { stdio: 'inherit', env: process.env })
process.exit(result.status ?? 1)
