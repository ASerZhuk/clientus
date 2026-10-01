import { z } from "zod";

const digits = (v: string) => v.replace(/\D/g, "");

export const phoneSchema = z
  .string()
  .trim()
  .refine((v) => digits(v).length >= 10 && digits(v).length <= 15, "Введите телефон полностью, например +7 900 123-45-67");

export const contactSchema = z.object({
  name: z.string().trim().min(1, "Введите имя").max(80, "Слишком длинное имя"),
  phone: phoneSchema,
  car: z.string().trim().min(1, "Укажите марку и модель").max(80),
  plate: z.string().trim().max(16, "Слишком длинный номер").optional().default(""),
});
export type ContactInput = z.input<typeof contactSchema>;

/** The booking form asks only what the business type needs (a car for a workshop, a note for a salon). */
export function contactSchemaFor(contact: { car: string; plate: string; note: string }) {
  return z.object({
    name: z.string().trim().min(1, "Введите имя").max(80, "Слишком длинное имя"),
    phone: phoneSchema,
    car: contact.car === "required" ? z.string().trim().min(1, "Укажите марку и модель").max(80) : z.string().trim().max(80).optional().default(""),
    plate: z.string().trim().max(16, "Слишком длинный номер").optional().default(""),
    note: z.string().trim().max(300, "Слишком длинный комментарий").optional().default(""),
  });
}

export const loginSchema = z.object({
  email: z.string().trim().min(3, "Введите почту").regex(/^[^@\s]+@[^@\s]+$/, "Похоже на неполный адрес"),
  password: z.string().min(1, "Введите пароль"),
});

const money = z.number({ error: "Введите сумму" }).min(0, "Не меньше нуля").max(1_000_000, "Слишком большая сумма");
export const serviceSchema = z.object({
  name: z.string().trim().min(1, "Введите название").max(120),
  description: z.string().trim().max(1000).default(""),
  price: money,
  duration_min: z.number({ error: "Введите длительность" }).int().min(15, "Минимум 15 минут").max(60 * 24 * 30),
  buffer_min: z.number({ error: "Введите время подготовки" }).int().min(0).max(60 * 24),
  resource_ids: z.array(z.number()).min(1, "Выберите хотя бы одно место"),
  is_active: z.boolean(),
});
export type ServiceForm = z.input<typeof serviceSchema>;

export const paymentSchema = z.object({
  kind: z.enum(["payment", "refund"]),
  amount: z.number({ error: "Введите сумму" }).positive("Сумма должна быть больше нуля").max(1_000_000),
  method: z.enum(["cash", "card", "transfer"]),
});

export const ownerBookingSchema = contactSchema.extend({
  car: z.string().trim().max(80).default(""),
  note: z.string().trim().max(300).default(""),
  service_id: z.number({ error: "Выберите услугу" }).int().positive("Выберите услугу"),
});

export const settingsSchema = z.object({
  name: z.string().trim().min(1, "Введите название").max(120),
  tagline: z.string().trim().max(200),
  description: z.string().trim().max(2000),
  phone: z.string().trim().max(32),
  address: z.string().trim().max(200),
  map_url: z
    .string()
    .trim()
    .max(300)
    .refine((v) => v === "" || /^https?:\/\//.test(v), "Ссылка должна начинаться с http:// или https://"),
  info_cards: z
    .array(z.object({ title: z.string().trim().min(1, "Введите заголовок").max(60), text: z.string().trim().min(1, "Введите текст").max(220), icon: z.string().default("sparkle") }))
    .max(3),
});

export function fieldErrors(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = issue.path.join(".");
    if (!(key in out)) out[key] = issue.message;
  }
  return out;
}
