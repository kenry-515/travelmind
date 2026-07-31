/**
 * Cross-page Navigation Tests (Phase 18 广州专属)
 *
 * Verifies all navigation paths work correctly:
 * - HomePage quick links → /guide, /chat, /image, /resources
 * - Search input → /chat?q=
 * - Keyboard shortcuts (Ctrl+K)
 * - Back navigation
 */

import { test, expect } from '@playwright/test'

test.describe('Navigation', () => {
  test('HomePage quick links navigate to correct pages', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Phase 18: 4 个快捷入口是 /guide /chat /image /resources(资源调度)
    const navLinks = page.locator('a[href^="/"]')
    const hrefs = await navLinks.evaluateAll((links) =>
      links.map((l) => (l as HTMLAnchorElement).getAttribute('href')).filter(Boolean)
    ) as string[]

    expect(hrefs).toContain('/guide')
    expect(hrefs).toContain('/chat')
    expect(hrefs).toContain('/image')
    expect(hrefs).toContain('/resources')
  })

  test('search input navigates to /chat?q=', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const searchInput = page.locator('input[type="text"], input[placeholder*="搜索"], input[placeholder*="想去"]')
    const count = await searchInput.count()
    if (count > 0) {
      await searchInput.first().fill('广州3日游')
      await searchInput.first().press('Enter')
      await page.waitForURL(/\/chat\?q=/, { timeout: 10000 })
      expect(page.url()).toContain('/chat?q=')
    }
  })

  test('Header back arrow returns to previous page', async ({ page }) => {
    // Phase 18: 真实路径 /resources(广州景区资源调度)
    await page.goto('/resources')
    await page.waitForLoadState('networkidle')

    // 使用精确的 aria-label 避免匹到无关 <a href="/">
    const backLink = page.locator('a[aria-label="返回首页"]').first()
    await expect(backLink).toBeVisible({ timeout: 5000 })
    await backLink.click()
    await page.waitForURL(/127\.0\.0\.1:5173\/$/, { timeout: 10000 })
    expect(page.url()).toMatch(/127\.0\.0\.1:5173\/$/)
  })

  test('Ctrl+K navigates to /chat', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    await page.keyboard.press('Control+k')
    await page.waitForURL('/chat', { timeout: 5000 })
    expect(page.url()).toContain('/chat')
  })
})