import { expect, test } from "@playwright/test";

test("beauty studio: choose a master, no car fields, master shown in the booking", async ({ page }) => {
  await page.goto("/s/loft-beauty");
  await expect(page.getByRole("heading", { name: "Мастера", level: 2 })).toBeVisible();
  for (const name of ["Анна", "Ольга", "Мария"]) await expect(page.locator(".master-card", { hasText: name })).toBeVisible();
  await page.locator("#hero").getByRole("button", { name: "Записаться" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("radio", { name: /Стрижка/ }).click();
  await expect(sheet.getByRole("heading", { name: "Выберите мастера" })).toBeVisible();
  await expect(sheet.getByText("Шаг 2 из 5")).toBeVisible();
  await expect(sheet.getByRole("radio", { name: /Любой свободный/ })).toBeVisible();
  await sheet.getByRole("radio", { name: /Мария/ }).click();
  await sheet.locator(".date-chip:not([disabled])").first().click();
  await sheet.locator(".slot:not([disabled])").first().click();
  await expect(sheet.getByRole("heading", { name: "Ваши данные" })).toBeVisible();
  await expect(sheet.getByLabel("Автомобиль")).toHaveCount(0);
  await expect(sheet.getByLabel("Госномер")).toHaveCount(0);
  await expect(sheet.getByText("1 800")).toBeVisible(); // Maria's own price for this service
  await sheet.getByLabel("Имя").fill("Мила Клиентка");
  await sheet.getByLabel("Телефон").fill("+7 900 222-33-44");
  await sheet.getByLabel("Комментарий").fill("Первый раз у вас");
  await sheet.getByRole("button", { name: "Подтвердить запись" }).click();
  await expect(sheet.getByRole("heading", { name: "Вы записаны" })).toBeVisible();
  await expect(sheet.getByText("Мария").first()).toBeVisible();
});

test("private master: no master step and no masters section", async ({ page }) => {
  await page.goto("/s/anna-nails");
  await expect(page.getByRole("heading", { name: "Мастера", level: 2 })).toHaveCount(0);
  await page.locator("#hero").getByRole("button", { name: "Записаться" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("radio").first().click();
  await expect(sheet.getByText("Шаг 2 из 4")).toBeVisible();
  await expect(sheet.getByRole("heading", { name: "Выберите дату" })).toBeVisible();
});

test("car wash: the form still asks for a car and uses 'бокс' wording", async ({ page }) => {
  await page.goto("/s/aqua-wash");
  await expect(page.getByText("бокса в работе")).toBeVisible();
  await page.locator("#hero").getByRole("button", { name: "Записаться" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("radio", { name: /Экспресс/ }).click();
  await sheet.locator(".date-chip:not([disabled])").first().click();
  await sheet.locator(".slot:not([disabled])").first().click();
  await expect(sheet.getByLabel("Автомобиль")).toBeVisible();
  await sheet.getByLabel("Имя").fill("Иван");
  await sheet.getByLabel("Телефон").fill("+7 900 555-66-77");
  await sheet.getByRole("button", { name: "Подтвердить запись" }).click();
  await expect(sheet.getByText("Укажите марку и модель")).toBeVisible();
});

test("owner of a salon edits a master's own schedule", async ({ page }) => {
  await page.goto("/s/loft-beauty/owner");
  await page.getByLabel("Почта").fill("owner@loft-beauty.example");
  await page.getByLabel("Пароль").fill("e2e-owner-password");
  await page.getByRole("button", { name: "Войти" }).click();
  await page.getByRole("link", { name: "Услуги" }).click();
  await expect(page.getByRole("heading", { name: "Мастера", level: 2 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Свой график" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Свой график" }).first().click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: /Расписание: Анна/ })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Сохранить расписание" }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: /Расписание/ })).toBeHidden();
});
