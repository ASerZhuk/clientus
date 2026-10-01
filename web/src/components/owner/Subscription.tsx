"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { useStudio } from "@/components/StudioProviders";
import { plural } from "@/lib/format";

export interface SubscriptionInfo {
  plan: string;
  plan_label: string;
  state: "preview" | "trial" | "active" | "past_due" | "suspended" | "disabled";
  ends_at: number | null;
  days_left: number | null;
  limits: { resources: number | null; bookings_month: number | null; custom_domain: boolean; remove_branding: boolean };
  usage: { bookings_month: number; resources: number };
}

const STATE_LABEL: Record<string, string> = { preview: "Образец", trial: "Пробный период", active: "Работает", past_due: "Ожидает оплаты", suspended: "Приостановлена", disabled: "Отключена" };

/** Shown on every cabinet screen when something needs the owner's attention. */
export function SubscriptionBanner({ sub }: { sub: SubscriptionInfo }) {
  const days = sub.days_left ?? 0;
  if (sub.state === "suspended" || sub.state === "disabled")
    return <Banner status="error" title="Кабинет работает только на просмотр" description="Подписка приостановлена: клиенты не могут записываться, а изменения в кабинете отключены. Свяжитесь с оператором сервиса, чтобы продлить." />;
  if (sub.state === "past_due")
    return <Banner status="warning" title="Срок оплаты истёк" description="Сервис пока работает. Продлите подписку, иначе онлайн-запись скоро будет приостановлена." />;
  if (sub.state === "trial" && days <= 7)
    return <Banner status="info" title={`Пробный период: осталось ${plural(days, ["день", "дня", "дней"])}`} description="Чтобы не потерять онлайн-запись, свяжитесь с оператором сервиса и выберите тариф." />;
  const nearLimit = sub.limits.bookings_month !== null && sub.usage.bookings_month >= sub.limits.bookings_month * 0.9;
  if (nearLimit) return <Banner status="warning" title="Скоро лимит записей на тарифе" description={`В этом месяце ${sub.usage.bookings_month} из ${sub.limits.bookings_month}. После лимита новые записи будут недоступны.`} />;
  return null;
}

export function TariffCard({ sub }: { sub: SubscriptionInfo }) {
  const { tenant } = useStudio();
  const lim = (v: number | null) => (v === null ? "без ограничений" : String(v));
  const end = sub.ends_at ? new Date(sub.ends_at * 1000).toLocaleDateString("ru-RU") : null;
  return (
    <div className="panel stack">
      <h2 className="section-title" style={{ margin: 0 }}>Ваш пакет</h2>
      <dl className="summary" style={{ margin: 0 }}>
        <div><dt>Пакет</dt><dd>{sub.plan_label}</dd></div>
        <div><dt>Статус</dt><dd>{STATE_LABEL[sub.state]}{end && sub.state !== "preview" ? ` · до ${end}` : sub.state === "active" ? " · бессрочно" : ""}</dd></div>
        <div><dt>Записей в этом месяце</dt><dd>{sub.usage.bookings_month}{sub.limits.bookings_month !== null ? ` из ${lim(sub.limits.bookings_month)}` : ""}</dd></div>
        <div><dt>Свой домен</dt><dd>{sub.limits.custom_domain ? "доступен" : "нет на этом тарифе"}</dd></div>
        <div><dt>Подпись «Работает на …»</dt><dd>{sub.limits.remove_branding ? "убрана" : "показывается"}</dd></div>
      </dl>
      <span className="muted" style={{ fontSize: 14 }}>
        Сменить пакет, подключить свой домен или перенести приложение на свой сервер — через автора сервиса
        {tenant.branding.url ? <> (<a href={tenant.branding.url} target="_blank" rel="noopener noreferrer">{tenant.branding.name}</a>)</> : null}.
      </span>
    </div>
  );
}
