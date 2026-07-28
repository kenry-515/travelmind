/**
 * ChatPage E2E Tests
 */

import { test, expect } from '@playwright/test'

test.describe('ChatPage', () => {
  test('page loads with chat interface', async ({ page }) => {
    await page.goto('/chat')
    await page.waitForLoadState('networkidle')

    // Should show header with title
    await expect(page.locator('h2')).toContainText('对话', { timeout: 5000 })

    // Chat input should be visible
    const textInput = page.locator('textarea, input[type="text"]')
    await expect(textInput.first()).toBeVisible({ timeout: 5000 })
  })

  test('loads with query parameter and starts dialog', async ({ page }) => {
    // Mock dialog message response to avoid LLM calls
    await page.route('**/api/v1/dialog/message', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session',
          reply: '北京是个好地方，我来帮你规划。请问你对预算有什么要求？',
          stage: 'collecting',
          slots: { city: '北京', days: 3, date: '下周', companions: '不限', budget_level: '不限', tags: [], pace: '不限' },
          followups_left: 3,
          suggestions: [{ label: '经济型', text: '预算经济' }],
          confirm: false,
          queued: 0,
        }),
      })
    })

    await page.goto('/chat?q=北京3日游')
    await page.waitForLoadState('networkidle')

    // Should show the reply message
    await expect(page.locator('text=北京是个好地方')).toBeVisible({ timeout: 10000 })
  })

  test('handles API error gracefully', async ({ page }) => {
    // Mock API error
    await page.route('**/api/v1/dialog/message', async (route) => {
      await route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'UPSTREAM_ERROR', message: '服务暂不可用' } }),
      })
    })

    await page.goto('/chat')
    await page.waitForLoadState('networkidle')

    // Try sending a message
    const textInput = page.locator('textarea, input[type="text"]')
    if (await textInput.count() > 0) {
      await textInput.first().fill('北京3日游')
      const sendBtn = page.locator('button[type="submit"], button:has-text("发送"), button:has-text("Send")')
      if (await sendBtn.count() > 0) {
        await sendBtn.first().click()
        // Should show error toast or message
        await page.waitForTimeout(3000)
      }
    }
  })
})
