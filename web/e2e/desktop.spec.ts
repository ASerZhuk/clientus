import { expect, test } from "@playwright/test";

test("desktop layout: booking card and navigation are usable", async ({ page }) => {
  await page.goto("/s/demo-tenant");
  await expect(page.getByRole("heading", { name: "Мотор-Сервис 24", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Записаться" }).first().click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Выберите услугу" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
