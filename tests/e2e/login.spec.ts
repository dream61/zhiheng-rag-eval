import { test, expect } from '../../frontend/node_modules/@playwright/test';
test('未登录时显示登录入口', async ({page}) => {
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'登录工作区'})).toBeVisible();
 await expect(page.getByLabel('用户名')).toBeVisible();
 await expect(page.getByLabel('密码')).toBeVisible();
});
