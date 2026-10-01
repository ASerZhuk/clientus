import { expect, test, type Page } from "@playwright/test";

const OWNER = { email: "owner@graphite.example", password: "e2e-owner-password" };

async function openSheet(page: Page) {
  await page.goto("/s/graphite");
  await expect(page.getByRole("heading", { name: "Запись в студию" })).toBeVisible();
  await page.locator("#hero").getByRole("button", { name: "Записаться" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "Выберите услугу" })).toBeVisible();
  await expect(sheet.getByText("Шаг 1 из 4")).toBeVisible();
  return sheet;
}

async function bookFirstFreeSlot(page: Page) {
  const flow = await openSheet(page);
  await flow.getByRole("radio", { name: /Керамическое покрытие/ }).click();
  await flow.locator(".date-chip:not([disabled])").first().click(); // moves on to the time step
  const slot = flow.locator(".slot:not([disabled])").first();
  await expect(slot).toBeVisible();
  const time = (await slot.textContent())!.trim();
  const date = await flow.locator(".date-chip[aria-pressed=true]").getAttribute("aria-label");
  await slot.click();
  await flow.getByLabel("Имя").fill("Иван E2E");
  await flow.getByLabel("Телефон").fill("+7 900 123-45-67");
  await flow.getByLabel("Автомобиль").fill("BMW X5");
  await flow.getByRole("button", { name: "Подтвердить запись" }).click();
  await expect(flow.getByRole("heading", { name: "Вы записаны" })).toBeVisible();
  return { time, date: date!, flow };
}

test("client books, owner sees it, the time can no longer be booked", async ({ page, browser, baseURL }) => {
  const { time, date, flow: done } = await bookFirstFreeSlot(page);
  await expect(done.getByText("Керамическое покрытие").first()).toBeVisible();
  await expect(done.getByRole("button", { name: "Добавить в календарь" })).toBeVisible();

  // "Моя запись" shows the same booking from the token kept on this device
  await done.getByRole("button", { name: "Моя запись" }).click();
  await expect(page.getByRole("heading", { name: "Моя запись" })).toBeVisible();
  await expect(page.locator(".studio").getByText("Запись подтверждена")).toBeVisible();

  // the ceramic box is the only suitable post: a second visitor sees that time as occupied
  const other = await browser.newContext({ baseURL });
  const p2 = await other.newPage();
  const flow = await openSheet(p2);
  await flow.getByRole("radio", { name: /Керамическое покрытие/ }).click();
  // a 2-day job started at the first slot: that whole day (and the next one) has no free start left
  const chip = flow.locator(`.date-chip[aria-label^="${date.split(", нет")[0]}"]`).first();
  await expect(chip).toBeDisabled();
  await expect(chip).toHaveAttribute("aria-label", /нет свободного времени/);
  void time;
  await other.close();

  // owner logs in and finds the booking in the schedule
  const ownerCtx = await browser.newContext({ baseURL });
  const o = await ownerCtx.newPage();
  await o.goto("/s/graphite/owner");
  await o.getByLabel("Почта").fill(OWNER.email);
  await o.getByLabel("Пароль").fill(OWNER.password);
  await o.getByRole("button", { name: "Войти" }).click();
  await expect(o.getByRole("heading", { name: "Расписание" })).toBeVisible();
  const weekLoaded = () => o.waitForResponse((r) => r.url().includes("/owner/schedule") && r.url().includes("days=7") && r.ok());
  let loaded = weekLoaded();
  await o.getByRole("radiogroup", { name: "Вид" }).getByRole("radio", { name: "Неделя" }).click();
  await loaded;
  for (let i = 0; i < 4 && (await o.getByText("Иван E2E").count()) === 0; i++) {
    loaded = weekLoaded();
    await o.getByRole("button", { name: "Вперёд" }).click();
    await loaded;
  }
  await o.getByText("Иван E2E").first().click();
  await expect(o.getByText("+7 900 123-45-67").or(o.getByText("79001234567")).first()).toBeVisible();
  await o.getByRole("button", { name: "Принять авто" }).click();
  await expect(o.getByText("Автомобиль принят").first()).toBeVisible();
  await ownerCtx.close();
});

test("wrong password is rejected and shows a message", async ({ page }) => {
  await page.goto("/s/graphite/owner");
  await page.getByLabel("Почта").fill(OWNER.email);
  await page.getByLabel("Пароль").fill("wrong-password-123");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByText("Неверная почта или пароль.")).toBeVisible();
});

test("deep links and manifest belong to the right studio", async ({ page, request }) => {
  for (const [slug, name] of [["graphite", "GRAPHITE Detailing"], ["demo-tenant", "Мотор-Сервис 24"]] as const) {
    await page.goto(`/s/${slug}/services`);
    await expect(page.getByRole("heading", { name: "Услуги и цены" })).toBeVisible();
    await expect(page.locator("link[rel=manifest]")).toHaveAttribute("href", `/s/${slug}/manifest.webmanifest`);
    const manifest = await (await request.get(`/s/${slug}/manifest.webmanifest`)).json();
    expect(manifest).toMatchObject({ id: `/s/${slug}/`, scope: `/s/${slug}/`, name, display: "standalone" });
  }
  expect((await request.get("/s/nope-studio/")).status()).toBe(404);
});
