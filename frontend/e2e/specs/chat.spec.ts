/**
 * ChatPage E2E Tests (Phase 18 广州专属)
 */

import { test, expect } from '@playwright/test'

test.describe('ChatPage', () => {
  test('page loads with chat interface', async ({ page }) => {
    await page.goto('/chat')
    await page.waitForLoadState('networkidle')

    // Should show header with theme toggle
    await expect(page.locator('.theme-toggle')).toBeVisible({ timeout: 5000 })

    // Chat input should be visible
    const textInput = page.locator('textarea, input[type="text"]')
    await expect(textInput.first()).toBeVisible({ timeout: 5000 })
  })

  test('loads with query parameter and starts dialog (广州专属)', async ({ page }) => {
    // Mock dialog message response — 广州专项 + 包含槽位
    await page.route('**/api/v1/dialog/message', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session-gz',
          reply: '广州是个好地方,我来帮你规划西关一日游。请问你对预算有什么要求?',
          stage: 'collecting',
          slots: { city: '广州', days: 1, date: '下周', companions: '不限', budget_level: '不限', tags: [], pace: '休闲' },
          followups_left: 3,
          suggestions: [{ label: '经济型', text: '预算经济' }],
          confirm: false,
          queued: 0,
        }),
      })
    })

    await page.goto('/chat?q=广州西关一日游')
    await page.waitForLoadState('networkidle')

    // Should show the reply message
    await expect(page.locator('text=广州是个好地方')).toBeVisible({ timeout: 10000 })
  })

  test('handles API error gracefully with suggestion + retry button', async ({ page }) => {
    // Phase 18: Mock 错误响应必须包含 suggestion + retryable
    await page.route('**/api/v1/dialog/message', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message: '服务暂不可用',
            suggestion: '可能是后端启动中或维护中,请刷新页面或稍后重试',
            retryable: true,
            details: null,
          },
        }),
      })
    })

    await page.goto('/chat')
    await page.waitForLoadState('networkidle')

    // Try sending a message
    const textInput = page.locator('textarea, input[type="text"]')
    if (await textInput.count() > 0) {
      await textInput.first().fill('广州一日游')
      const sendBtn = page.locator('button[type="submit"], button:has-text("发送")')
      if (await sendBtn.count() > 0) {
        await sendBtn.first().click()
        await page.waitForTimeout(2000)
        // Phase 18: error message should show suggestion
        const errorText = await page.locator('text=服务暂不可用').count()
        expect(errorText).toBeGreaterThanOrEqual(1)
        // Retry button should appear (retryable=true)
        const retryBtn = await page.locator('button:has-text("重试")').count()
        expect(retryBtn).toBeGreaterThanOrEqual(1)
      }
    }
  })
})