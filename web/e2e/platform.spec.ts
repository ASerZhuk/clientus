import { expect, test } from "@playwright/test";

const CUSTOM = "http://book.aqua.test:13100";

test("a customer's own domain serves that studio at the root with clean links", async ({ page }) => {
  await page.goto(`${CUSTOM}/`);
  await expect(page.getByRole("heading", { name: "АкваДрайв", level: 1 })).toBeVisible();
  await expect(page.locator("link[rel=manifest]")).toHaveAttribute("href", "/manifest.webmanifest");
  const manifest = await page.evaluate(() => fetch("/manifest.webmanifest").then((r) => r.json()));
  expect(manifest).toMatchObject({ id: "/", scope: "/", name: "АкваДрайв" });
  await expect(page.getByText("Работает на")).toBeVisible(); // an own domain alone keeps the line
  await page.getByRole("link", { name: "Услуги", exact: true }).first().click();
  await expect(page).toHaveURL(`${CUSTOM}/services`);
  await expect(page.getByRole("heading", { name: "Услуги и цены" })).toBeVisible();

  // a full booking works on the custom domain (API calls stay on the same origin)
  await page.goto(`${CUSTOM}/`);
  await page.locator("#hero").getByRole("button", { name: "Записаться" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("radio", { name: /Экспресс/ }).click();
  await sheet.locator(".date-chip:not([disabled])").first().click();
  await sheet.locator(".slot:not([disabled])").first().click();
  await sheet.getByLabel("Имя").fill("Клиент домена");
  await sheet.getByLabel("Телефон").fill("+7 900 777-88-99");
  await sheet.getByLabel("Автомобиль").fill("Kia Rio");
  await sheet.getByRole("button", { name: "Подтвердить запись" }).click();
  await expect(sheet.getByRole("heading", { name: "Вы записаны" })).toBeVisible();
  await sheet.getByRole("button", { name: "Моя запись" }).click();
  await expect(page).toHaveURL(`${CUSTOM}/my`);
  await expect(page.locator(".studio").getByText("Запись подтверждена")).toBeVisible();
});

test("a customer's domain cannot reach other studios, the operator panel or unknown hosts", async ({ page }) => {
  expect((await page.goto(`${CUSTOM}/s/loft-beauty`))!.status()).toBe(404);
  expect((await page.goto(`${CUSTOM}/admin`))!.status()).toBe(404);
  expect((await page.goto("http://unknown.test:13100/"))!.status()).toBe(404);
  expect((await page.goto("/admin"))!.status()).toBe(200); // the platform host serves the panel
});

test("«Работает на …» is hidden only on the own-server package", async ({ page }) => {
  await page.goto("/s/demo-tenant"); // standard
  await expect(page.getByText("Работает на")).toBeVisible();
  await page.goto("/s/graphite"); // domain package
  await expect(page.getByText("Работает на")).toBeVisible();
  await page.goto("/s/loft-beauty"); // self_hosted
  await expect(page.getByRole("heading", { name: "Loft Beauty", level: 1 })).toBeVisible();
  await expect(page.getByText("Работает на")).toHaveCount(0);
});

test("operator suspends a studio: customers cannot book, the owner is read-only; resume restores it", async ({ page, browser }) => {
  await page.goto("/admin");
  await page.getByLabel("Почта").fill("boss@platform.test");
  await page.getByLabel("Пароль").fill("e2e-operator-password");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("heading", { name: "Студии", level: 1 })).toBeVisible();
  await expect(page.locator(".svc-row", { hasText: "Loft Beauty" })).toBeVisible();
  await page.locator(".svc-row", { hasText: "Анна · маникюр" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "Анна · маникюр" })).toBeVisible();
  await sheet.getByRole("button", { name: "Приостановить" }).click();
  await expect(sheet.getByRole("button", { name: "Возобновить" })).toBeVisible();

  const customer = await browser.newContext();
  const p = await customer.newPage();
  await p.goto("http://127.0.0.1:13100/s/anna-nails");
  await p.locator("#hero").getByRole("button", { name: "Записаться" }).click();
  await expect(p.getByRole("dialog").getByText("Онлайн-запись временно недоступна")).toBeVisible();
  await customer.close();

  const owner = await browser.newContext();
  const o = await owner.newPage();
  await o.goto("http://127.0.0.1:13100/s/anna-nails/owner");
  await o.getByLabel("Почта").fill("owner@anna-nails.example");
  await o.getByLabel("Пароль").fill("e2e-owner-password");
  await o.getByRole("button", { name: "Войти" }).click();
  await expect(o.getByText("Кабинет работает только на просмотр")).toBeVisible();
  await owner.close();

  await sheet.getByRole("button", { name: "Возобновить" }).click();
  await expect(sheet.getByRole("button", { name: "Приостановить" })).toBeVisible();
});
