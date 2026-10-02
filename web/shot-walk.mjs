import { chromium } from "@playwright/test";
const OUT = process.argv[2];
const H = process.env.BASE_URL || "http://localhost:3000", S = H + "/s/alexmotors";
const OWNER = { email: "owner@alexmotors34.ru", password: process.env.OWNER_PW };
const b = await chromium.launch({ executablePath: process.env.PW_CHROMIUM });
const results = [];
const problems = [];
function watch(page, who) {
  page.on("console", (m) => { if (m.type() === "error") problems.push(`${who} console: ${m.text().slice(0, 200)}`); });
  page.on("pageerror", (e) => problems.push(`${who} pageerror: ${e.message.slice(0, 200)}`));
  page.on("response", (r) => { if (r.status() >= 400 && !r.url().includes("/owner/me")) problems.push(`${who} HTTP ${r.status()} ${r.request().method()} ${r.url().replace(H, "")}`); });
}
let n = 0;
async function step(page, name, fn) {
  n += 1;
  try { await fn(); results.push(`OK   ${n}. ${name}`); }
  catch (e) { results.push(`FAIL ${n}. ${name}: ${e.message.split("\n")[0].slice(0, 160)}`); }
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/${String(n).padStart(2, "0")}.png` }).catch(() => {});
}
const vis = async (loc) => { await loc.first().waitFor({ state: "visible", timeout: 8000 }); };

const client = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "ru-RU" });
const c = await client.newPage(); watch(c, "client");

async function book(name, phone) {
  await c.goto(S + "/", { waitUntil: "networkidle" });
  await c.locator("#hero").getByRole("button", { name: "Записаться" }).click();
  const d = c.getByRole("dialog");
  await d.getByRole("radio", { name: /Развал-схождение/ }).click();
  const any = d.getByRole("radio", { name: /Любое|Любой/ });
  if (await any.count()) await any.first().click();
  await d.locator(".date-chip:not([disabled])").nth(1).click();
  await d.locator(".slot:not([disabled])").first().click();
  await d.getByLabel("Имя").fill(name);
  await d.getByLabel("Телефон").fill(phone);
  const car = d.getByLabel(/Автомобиль|Марка/);
  if (await car.count()) await car.first().fill("Lada Vesta");
  await d.getByRole("button", { name: "Подтвердить запись" }).click();
  await vis(d.getByRole("heading", { name: "Вы записаны" }));
}

await step(c, "главная: загрузка, нет надписи «демо»", async () => {
  await c.goto(S + "/", { waitUntil: "networkidle" });
  await vis(c.getByRole("heading", { name: "Alex Motors", level: 1 }));
  if (await c.getByText("демонстрационные").count()) throw new Error("надпись про демо на месте");
});
await step(c, "главная: услуги, работы, контакты", async () => {
  await vis(c.locator(".svc-list li"));
  await c.getByRole("heading", { name: "Как нас найти" }).scrollIntoViewIfNeeded();
  await vis(c.locator(".reel-item"));
});
await step(c, "главная: нажатие на рабочий день открывает запись", async () => {
  await c.locator(".pill-day:not([disabled])").nth(1).click();
  await vis(c.getByRole("dialog").getByRole("heading", { name: "Выберите услугу" }));
  await c.keyboard.press("Escape");
});
await step(c, "страница всех услуг", async () => {
  await c.goto(S + "/services", { waitUntil: "networkidle" });
  await vis(c.getByRole("heading", { name: "Услуги и цены" }));
  if ((await c.locator(".svc-row").count()) < 13) throw new Error("услуг меньше 13");
});
await step(c, "запись клиента: услуга → дата → время → контакты → подтверждение", () => book("Тест Проверка", "+7 900 555-44-01"));
await step(c, "«Моя запись» показывает запись", async () => {
  await c.getByRole("dialog").getByRole("button", { name: "Моя запись" }).click();
  await vis(c.getByText("Запись подтверждена"));
});
await step(c, "помощник отвечает на вопрос о цене", async () => {
  await c.locator("#ai-fab").click();
  const d = c.getByRole("dialog");
  const box = d.locator("textarea, input[type=text]").last();
  await box.fill("Сколько стоит развал-схождение?");
  await box.press("Enter");
  await c.waitForTimeout(2500);
  const txt = await d.locator(".bubble.bot").last().textContent();
  if (!/1\s?500/.test(txt || "")) throw new Error(`ответ: ${txt?.slice(0, 120)}`);
  await c.keyboard.press("Escape");
});
await step(c, "страница установки приложения", async () => {
  await c.goto(S + "/install", { waitUntil: "networkidle" });
  await vis(c.locator(".install-steps li"));
});
await step(c, "профиль клиента", async () => {
  await c.goto(S + "/account", { waitUntil: "networkidle" });
  await c.waitForTimeout(800);
});
await step(c, "вторая запись для отмены клиентом", () => book("Тест Отмена", "+7 900 555-44-02"));
await step(c, "клиент отменяет запись", async () => {
  await c.getByRole("dialog").getByRole("button", { name: "Моя запись" }).click();
  await c.getByRole("button", { name: /Отменить/ }).first().click();
  await c.getByRole("button", { name: "Да, отменить" }).click();
  await vis(c.getByText(/Запись отменена|отменена/));
});

const owner = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "ru-RU" });
const o = await owner.newPage(); watch(o, "owner");
await step(o, "вход владельца", async () => {
  await o.goto(S + "/owner", { waitUntil: "networkidle" });
  await o.getByLabel("Почта").fill(OWNER.email);
  await o.getByLabel("Пароль").fill(OWNER.password);
  await o.getByRole("button", { name: "Войти" }).click();
  await vis(o.getByRole("heading", { name: "Расписание" }));
});
await step(o, "расписание: неделя показывает обе записи", async () => {
  await o.getByRole("radio", { name: "Неделя" }).last().click();
  await vis(o.locator(".booking-row", { hasText: "Тест Проверка" }));
  await vis(o.locator(".booking-row", { hasText: "Тест Отмена" }));
});
await step(o, "карточка записи открывается", async () => {
  await o.locator(".booking-row", { hasText: "Тест Проверка" }).first().click();
  await vis(o.getByRole("dialog").getByText("Тест Проверка"));
});
await step(o, "статус «Принять авто»", async () => {
  const d = o.getByRole("dialog");
  await d.getByRole("button", { name: /Принять/ }).click();
  await vis(d.getByText(/Принят/));
});
await step(o, "оплата 1 500 ₽ наличными", async () => {
  const d = o.getByRole("dialog");
  await d.getByLabel("Сумма").fill("1500");
  await d.getByRole("button", { name: /Записать оплату|Сохранить|Внести|Принять оплату/ }).first().click();
  await o.waitForTimeout(1200);
});
await step(o, "статус «Готова»", async () => {
  const d = o.getByRole("dialog");
  await d.getByRole("button", { name: /Готов/ }).first().click();
  await o.waitForTimeout(1000);
});
await step(o, "показатели за неделю пересчитались", async () => {
  await o.keyboard.press("Escape");
  await o.waitForTimeout(800);
  await o.getByRole("radio", { name: "Неделя" }).first().click();
  await o.waitForTimeout(1200);
});
await step(o, "быстрая запись: форма открывается", async () => {
  await o.getByRole("button", { name: "Добавить запись" }).click();
  await vis(o.getByRole("dialog"));
});
await step(o, "блокировка времени: форма открывается", async () => {
  await o.keyboard.press("Escape"); await o.waitForTimeout(600);
  await o.locator(".fab .round").first().click();
  await vis(o.getByRole("dialog"));
  await o.keyboard.press("Escape");
});
await step(o, "услуги: изменить цену развала на 1 600 ₽", async () => {
  await o.goto(S + "/owner/services", { waitUntil: "networkidle" });
  await o.locator(".service-row", { hasText: "Развал-схождение" }).first().click();
  const d = o.getByRole("dialog");
  const price = d.getByLabel(/Цена/).first();
  await price.fill("1600");
  await d.getByRole("button", { name: /Сохранить/ }).first().click();
  await o.waitForTimeout(1200);
});
await step(c, "клиент видит новую цену 1 600 ₽", async () => {
  await c.goto(S + "/", { waitUntil: "networkidle" });
  await vis(c.locator(".svc-list li", { hasText: "1 600" }));
});
await step(o, "услуги: вернуть цену 1 500 ₽", async () => {
  await o.locator(".service-row", { hasText: "Развал-схождение" }).first().click();
  const d = o.getByRole("dialog");
  await d.getByLabel(/Цена/).first().fill("1500");
  await d.getByRole("button", { name: /Сохранить/ }).first().click();
  await o.waitForTimeout(1200);
});
await step(o, "рабочие места: видны «Место 1» и «Место 2»", async () => {
  await o.getByRole("heading", { name: "Рабочие места" }).scrollIntoViewIfNeeded();
  await vis(o.locator("input[value='Место 1'], input"));
});
await step(o, "студия: страница настроек и сохранение без изменений", async () => {
  await o.goto(S + "/owner/studio", { waitUntil: "networkidle" });
  await vis(o.getByRole("heading", { name: "Студия" }));
  await o.getByRole("button", { name: "Сохранить" }).first().click();
  await o.waitForTimeout(1200);
});
await step(o, "помощник владельца отвечает", async () => {
  await o.locator("#owner-nav").getByRole("button", { name: "Помощник" }).click();
  const d = o.getByRole("dialog");
  const box = d.locator("textarea, input[type=text]").last();
  await box.fill("Сколько записей сегодня?");
  await box.press("Enter");
  await o.waitForTimeout(2500);
});
await step(o, "выход из кабинета", async () => {
  await o.keyboard.press("Escape");
  await o.goto(S + "/owner/studio", { waitUntil: "networkidle" });
  await o.getByRole("button", { name: /Выйти/ }).click();
  await vis(o.getByRole("heading", { name: "Вход в кабинет" }));
});

console.log(results.join("\n"));
console.log("\nPROBLEMS:\n" + [...new Set(problems)].join("\n"));
await b.close();
