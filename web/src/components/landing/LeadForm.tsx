"use client";

import { CheckCircle, PaperPlaneRight } from "@phosphor-icons/react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

const KINDS = [
  { value: "auto", label: "Автосервис" },
  { value: "wash", label: "Мойка" },
  { value: "beauty_master", label: "Мастер" },
  { value: "beauty_studio", label: "Студия красоты" },
  { value: "other", label: "Другое" },
];

/** Three required things only: name, phone, kind of business. The rest is optional. */
export function LeadForm() {
  const [f, setF] = useState({ name: "", phone: "", kind: "", business: "", city: "", comment: "", website: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!f.name.trim()) next.name = "Как к вам обращаться?";
    const digits = f.phone.replace(/\D/g, "");
    if (digits.length < 10 || digits.length > 15) next.phone = "Нужен номер телефона, например +7 900 000-00-00";
    if (!f.kind) next.kind = "Выберите вид бизнеса";
    setErrors(next);
    if (Object.keys(next).length) {
      document.getElementById(`lead-${Object.keys(next)[0]}`)?.focus();
      return;
    }
    setState("sending");
    try {
      await api("/api/leads", { method: "POST", body: f });
      setState("done");
    } catch (err) {
      setState("error");
      setErrors({ form: err instanceof ApiError ? err.message : "Не удалось отправить. Попробуйте ещё раз." });
    }
  };

  if (state === "done")
    return (
      <div className="lp-card lp-done" role="status">
        <CheckCircle size={44} weight="fill" aria-hidden />
        <h3>Заявка отправлена</h3>
        <p>Спасибо, {f.name.trim()}! Перезвоним на {f.phone} в течение дня.</p>
      </div>
    );

  return (
    <form className="lp-card lp-form" onSubmit={submit} noValidate>
      <label className="lp-field">
        <span>Имя *</span>
        <input id="lead-name" autoComplete="name" value={f.name} onChange={set("name")} aria-invalid={!!errors.name} placeholder="Андрей" />
        {errors.name && <em role="alert">{errors.name}</em>}
      </label>
      <label className="lp-field">
        <span>Телефон *</span>
        <input id="lead-phone" type="tel" inputMode="tel" autoComplete="tel" value={f.phone} onChange={set("phone")} aria-invalid={!!errors.phone} placeholder="+7 900 000-00-00" />
        {errors.phone && <em role="alert">{errors.phone}</em>}
      </label>
      <fieldset className="lp-field">
        <legend>Вид бизнеса *</legend>
        <div className="lp-chips" id="lead-kind" tabIndex={-1}>
          {KINDS.map((k) => (
            <button key={k.value} type="button" aria-pressed={f.kind === k.value} onClick={() => setF({ ...f, kind: k.value })}>{k.label}</button>
          ))}
        </div>
        {errors.kind && <em role="alert">{errors.kind}</em>}
      </fieldset>
      <div className="lp-two">
        <label className="lp-field"><span>Название</span><input autoComplete="organization" value={f.business} onChange={set("business")} placeholder="Alex Motors" /></label>
        <label className="lp-field"><span>Город</span><input autoComplete="address-level2" value={f.city} onChange={set("city")} placeholder="Волгоград" /></label>
      </div>
      <label className="lp-field"><span>Комментарий</span><textarea rows={3} value={f.comment} onChange={set("comment")} placeholder="Сколько боксов или мастеров, что важно в записи" /></label>
      <label className="lp-hp" aria-hidden>Сайт<input tabIndex={-1} autoComplete="off" value={f.website} onChange={set("website")} /></label>
      {errors.form && <em className="lp-form-error" role="alert">{errors.form}</em>}
      <button type="submit" className="lp-btn lp-btn-block" disabled={state === "sending"}>
        {state === "sending" ? "Отправляем…" : <>Отправить заявку <PaperPlaneRight weight="fill" aria-hidden /></>}
      </button>
      <small className="lp-note">Нажимая кнопку, вы соглашаетесь на обработку контактных данных для связи по заявке.</small>
    </form>
  );
}
