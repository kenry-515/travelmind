import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E 配置（Phase 18 M5）
 *
 * - 默认 baseURL = http://localhost:5173 (Vite dev server)
 * - 自动启动 vite（如未运行）作为 webServer
 * - 后端必须在 8000 端口先启动（docker compose up postgres+redis+backend）
 * - 仅在本地 + CI 启用 headless（CI 标准）
 *
 * 首次运行需要: npx playwright install chromium
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'list',

  // 启动 vite dev server（如未运行）
  // 关闭 webServer: 用户需手动启动 vite + backend（docker compose up backend）
  // 原因: E2E 测试需要 backend 在 8000 端口,先 docker 起 backend 比加一个启动器简单。
  webServer: {
    command: 'npx vite --port 5173 --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,  // 总是用已存在的 vite,本地测试方便
    timeout: 60_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },

  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'zh-CN',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})