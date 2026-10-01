import { describe, expect, it } from "vitest";
import { contactSchema, fieldErrors, loginSchema, paymentSchema, serviceSchema, settingsSchema } from "./schemas";

describe("contact form", () => {
  it("accepts a normal booking contact", () => {
    expect(contactSchema.safeParse({ name: " Иван ", phone: "+7 900 123-45-67", car: "BMW X5" }).success).toBe(true);
  });
  it("explains what is wrong in Russian", () => {
    const r = contactSchema.safeParse({ name: "", phone: "123", car: "" });
    expect(r.success).toBe(false);
    if (!r.success) {
      const e = fieldErrors(r.error);
      expect(e.name).toBe("Введите имя");
      expect(e.phone).toContain("телефон");
      expect(e.car).toBe("Укажите марку и модель");
    }
  });
});

describe("owner forms", () => {
  it("rejects a malformed login", () => {
    expect(loginSchema.safeParse({ email: "nope", password: "x" }).success).toBe(false);
    expect(loginSchema.safeParse({ email: "a@b.c", password: "x" }).success).toBe(true);
  });
  it("service needs a post, a positive duration and a non-negative price", () => {
    const ok = { name: "Мойка", description: "", price: 1000, duration_min: 60, buffer_min: 0, resource_ids: [1], is_active: true };
    expect(serviceSchema.safeParse(ok).success).toBe(true);
    expect(serviceSchema.safeParse({ ...ok, resource_ids: [] }).success).toBe(false);
    expect(serviceSchema.safeParse({ ...ok, duration_min: 0 }).success).toBe(false);
    expect(serviceSchema.safeParse({ ...ok, price: -1 }).success).toBe(false);
  });
  it("payment amount must be positive", () => {
    expect(paymentSchema.safeParse({ kind: "refund", amount: 0, method: "cash" }).success).toBe(false);
    expect(paymentSchema.safeParse({ kind: "payment", amount: 10.5, method: "card" }).success).toBe(true);
  });
  it("settings: at most three cards and http(s) map links", () => {
    const base = { name: "S", tagline: "", description: "", phone: "", address: "", map_url: "", info_cards: [] };
    expect(settingsSchema.safeParse(base).success).toBe(true);
    expect(settingsSchema.safeParse({ ...base, map_url: "javascript:alert(1)" }).success).toBe(false);
    const card = { title: "a", text: "b", icon: "star" };
    expect(settingsSchema.safeParse({ ...base, info_cards: [card, card, card, card] }).success).toBe(false);
  });
});
