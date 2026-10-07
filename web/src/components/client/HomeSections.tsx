"use client";

import { ArrowRight, ArrowUpRight, CaretRight, DownloadSimple, Export, MapPin, NavigationArrow, Phone, User, X } from "@phosphor-icons/react";
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useProfile, useStudio, useVocab } from "@/components/StudioProviders";
import { Reveal } from "@/components/ui/Reveal";
import { formatDurationShort, formatMoney, telHref, todayKey } from "@/lib/format";
import { useMounted } from "@/lib/hooks";
import { useInstall } from "@/lib/install";
import { useBooking } from "./BookingProvider";

const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
type Tenant = ReturnType<typeof useStudio>["tenant"];

function useToday() {
  const { tenant } = useStudio();
  const mounted = useMounted();
  const index = mounted ? (new Date(`${todayKey(tenant.timezone)}T12:00:00Z`).getUTCDay() + 6) % 7 : -1;
  return { index, day: index >= 0 ? tenant.hours[index] : undefined };
}

function mapHref(tenant: Tenant) {
  return tenant.map_url || (tenant.address ? `https://yandex.ru/maps/?text=${encodeURIComponent(tenant.address)}` : "");
}

/** Info tokens may use live values so they never go stale: {services}, {resources}, {min_price}. */
function fillTokens(text: string, tenant: Tenant): string {
  const prices = tenant.services.map((s) => s.price_minor);
  const counts: Record<string, number> = { services: tenant.services.length, resources: tenant.resources_count };
  const word = (n: number, forms: string[]) => {
    const n10 = n % 10, n100 = n % 100;
    return n10 === 1 && n100 !== 11 ? forms[0] : n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? forms[1] : forms[2];
  };
  return text
    .replace(/\{(services|resources)_word:([^|}]+)\|([^|}]+)\|([^}]+)\}/g, (_m, k: string, a: string, b: string, c: string) => word(counts[k], [a, b, c]))
    .replace("{services}", String(tenant.services.length))
    .replace("{resources}", String(tenant.resources_count))
    .replace("{min_price}", prices.length ? formatMoney(Math.min(...prices), tenant.currency) : "—");
}

/** Full-screen photo opener: brand bar on top, name, status and the one light action at the bottom. */
export function Hero() {
  const { tenant, href } = useStudio();
  const booking = useBooking();
  const { day } = useToday();
  const open = day && !day.closed && day.open;
  return (
    <section className="hero" id="hero">
      {tenant.hero_url && <Image className="hero-photo" src={tenant.hero_url} alt="" fill priority sizes="100vw" unoptimized />}
      <div className="hero-bar">
        <span className="hero-logo">{tenant.logo_url ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={tenant.logo_url} alt="" /> : tenant.name.slice(0, 1)}</span>
        <span className="grow" />
        <Link href={href("/account")} className="glass-round" aria-label="Профиль"><User size={20} aria-hidden /></Link>
      </div>
      <div className="hero-foot">
        <p className="hero-meta">
          {day && <span className={`status ${open ? "on" : ""}`}><i aria-hidden />{open ? `Открыто до ${day.close}` : "Сегодня закрыто"}</span>}
          {tenant.address && <span>{tenant.address.split(",")[0]}</span>}
        </p>
        <h1 className="hero-name">{tenant.name}</h1>
        {tenant.tagline && <p className="hero-tagline">{tenant.tagline}</p>}
        <div className="hero-actions">
          <button type="button" id="hero-cta" className="cream-btn" onClick={() => booking.open()}>Записаться <ArrowUpRight size={20} weight="bold" aria-hidden /></button>
          {tenant.phone && <a className="glass-round lg" href={telHref(tenant.phone)} aria-label={`Позвонить: ${tenant.phone}`}><Phone size={22} aria-hidden /></a>}
        </div>
      </div>
    </section>
  );
}

function Facts() {
  const { tenant } = useStudio();
  if (!tenant.info_cards.length) return null;
  return (
    <dl className="page facts">
      {tenant.info_cards.map((c, i) => (
        <div key={i}><dt>{fillTokens(c.title, tenant)}</dt><dd>{fillTokens(c.text, tenant)}</dd></div>
      ))}
    </dl>
  );
}

/** The next seven days with the studio's hours; closed days cannot be picked. */
function DayPills() {
  const { tenant } = useStudio();
  const booking = useBooking();
  const vocab = useVocab();
  const mounted = useMounted();
  const start = new Date(`${todayKey(tenant.timezone)}T12:00:00Z`);
  const days = mounted ? Array.from({ length: 7 }, (_, i) => new Date(start.getTime() + i * 86_400_000)) : [];
  return (
    <section className="page sect" aria-labelledby="days-title">
      <div className="sect-head"><h2 id="days-title">{vocab("book_title")}</h2></div>
      <div className="pills" role="list" aria-label="Ближайшие дни">
        {days.map((d, i) => {
          const wd = (d.getUTCDay() + 6) % 7;
          const h = tenant.hours[wd];
          const off = !h || h.closed || !h.open;
          return (
            <button key={i} type="button" role="listitem" className={`pill-day ${i === 0 ? "today" : ""}`} disabled={off} onClick={() => booking.open()} aria-label={`${DAYS[wd]} ${d.getUTCDate()}: ${off ? "выходной" : `${h.open}–${h.close}`}`}>
              <small>{i === 0 ? "Сегодня" : DAYS[wd]}</small>
              <b>{d.getUTCDate()}</b>
              <em>{off ? "вых." : `${Number(h.open!.slice(0, 2))}–${Number(h.close!.slice(0, 2))}`}</em>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function ServiceList({ limit }: { limit: number }) {
  const { tenant, href } = useStudio();
  const booking = useBooking();
  const list = tenant.services.slice(0, limit);
  return (
    <Reveal className="page sect" aria-labelledby="services-title">
      <div className="sect-head">
        <h2 id="services-title">Услуги</h2>
        {tenant.services.length > limit && <Link href={href("/services")} className="sect-link">Все {tenant.services.length} <ArrowRight size={16} aria-hidden /></Link>}
      </div>
      <ul className="svc-list">
        {list.map((s) => (
          <li key={s.id}>
            <button type="button" disabled={!s.bookable} onClick={() => booking.open({ serviceId: s.id })}>
              <span className="grow"><b>{s.name}</b><small>{formatDurationShort(s.duration_min)}</small></span>
              <span className="svc-price">{s.price_varies ? "от " : ""}{formatMoney(s.price_minor, tenant.currency)}</span>
              <CaretRight size={18} aria-hidden />
            </button>
          </li>
        ))}
        {list.length === 0 && <li className="muted">Услуги скоро появятся.</li>}
      </ul>
    </Reveal>
  );
}

function WorksReel() {
  const { tenant } = useStudio();
  const vocab = useVocab();
  if (!tenant.gallery.length) return null;
  return (
    <Reveal className="sect" aria-labelledby="works-title">
      <div className="page sect-head"><h2 id="works-title">{vocab("works_title")}</h2></div>
      <div className="reel">
        {tenant.gallery.map((g, i) => (
          <figure key={g.id} className="reel-item">
            <Image src={g.url} alt={g.caption || `Работа ${i + 1}`} fill sizes="(max-width: 600px) 82vw, 420px" loading={i < 2 ? "eager" : "lazy"} unoptimized />
            {g.caption && <figcaption>{g.caption}</figcaption>}
          </figure>
        ))}
      </div>
    </Reveal>
  );
}

export function Masters() {
  const { tenant } = useStudio();
  const vocab = useVocab();
  const booking = useBooking();
  if (!tenant.resources.length) return null;
  return (
    <Reveal className="sect" aria-labelledby="masters-title">
      <div className="page sect-head"><h2 id="masters-title">{vocab("resource_section")}</h2></div>
      <div className="reel">
        {tenant.resources.map((m) => (
          <button key={m.id} type="button" className="master-card" onClick={() => booking.open()}>
            {m.photo_url ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={m.photo_url} alt="" /> : <span className="master-initial" aria-hidden>{m.name.slice(0, 1)}</span>}
            <span className="master-text"><b>{m.name}</b>{m.description && <span>{m.description}</span>}</span>
          </button>
        ))}
      </div>
    </Reveal>
  );
}

function Visit() {
  const { tenant } = useStudio();
  const { index } = useToday();
  const map = mapHref(tenant);
  return (
    <Reveal className="page sect" aria-labelledby="visit-title">
      <div className="sect-head"><h2 id="visit-title">Как нас найти</h2></div>
      <div className="visit">
        {tenant.address && <p className="visit-addr"><MapPin size={20} aria-hidden /><span>{tenant.address}</span></p>}
        <ul className="week">
          {tenant.hours.map((h, i) => (
            <li key={i} aria-current={i === index ? "date" : undefined}><span>{DAYS[i]}</span><span>{h.closed || !h.open ? "выходной" : `${h.open}–${h.close}`}</span></li>
          ))}
        </ul>
        <div className="visit-actions">
          {map && <a className="line-btn" href={map} target="_blank" rel="noopener noreferrer"><NavigationArrow size={18} aria-hidden /> Маршрут</a>}
          {tenant.phone && <a className="line-btn" href={telHref(tenant.phone)}><Phone size={18} aria-hidden /> {tenant.phone}</a>}
        </div>
      </div>
    </Reveal>
  );
}

export function InstallCard() {
  const { tenant, href } = useStudio();
  const { state, install } = useInstall();
  const [iosHint, setIosHint] = useState(false);
  if (state === "installed") return null;
  const body = (
    <>
      <span className="logo">{tenant.logo_url ? /* eslint-disable-next-line @next/next/no-img-element */ <img src={tenant.pwa.icon192} alt="" /> : null}</span>
      <span className="grow"><b>Приложение {tenant.name}</b><small>{state === "prompt" ? "Установить в одно касание" : "Добавьте на экран — запись в пару касаний"}</small></span>
      <DownloadSimple size={22} aria-hidden />
    </>
  );
  return (
    <Reveal className="page sect" aria-label="Установка приложения">
      {state === "prompt" || state === "ios" ? (
        <button type="button" className="install-row" onClick={() => (state === "prompt" ? install() : setIosHint(true))}>{body}</button>
      ) : (
        <Link href={href("/install")} className="install-row">{body}</Link>
      )}
      {iosHint && <IosInstallHint onClose={() => setIosHint(false)} />}
    </Reveal>
  );
}

/** Apple lets no site start an install: point at Safari's Share button and the one menu item to tap. */
function IosInstallHint({ onClose }: { onClose: () => void }) {
  return (
    <div className="ios-hint-backdrop" role="presentation" onClick={onClose}>
      <div className="ios-hint" role="dialog" aria-modal="true" aria-label="Как установить на iPhone" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="ios-hint-close" aria-label="Закрыть" onClick={onClose}><X size={18} aria-hidden /></button>
        <p><b>1.</b> Нажмите <Export size={20} weight="bold" aria-label="Поделиться" className="ios-share" /> «Поделиться» внизу Safari (в новых iOS — сначала «…»)</p>
        <p><b>2.</b> Выберите «На экран Домой» → «Добавить»</p>
        <span className="ios-hint-arrow" aria-hidden />
      </div>
    </div>
  );
}

export function ServicesPanel({ limit, withHeading = true }: { limit?: number; withHeading?: boolean }) {
  const { tenant, href } = useStudio();
  const booking = useBooking();
  const list = limit ? tenant.services.slice(0, limit) : tenant.services;
  return (
    <Reveal className="page section" aria-labelledby="services-title">
      {withHeading && (
        <div className="section-head">
          <h2 id="services-title" className="section-title">Услуги</h2>
          <Link href={href("/services")} className="link-muted">Все услуги <ArrowRight size={20} aria-hidden /></Link>
        </div>
      )}
      <div className="svc-panel">
        {list.map((s) => (
          <button key={s.id} type="button" className="svc-row" disabled={!s.bookable} onClick={() => booking.open({ serviceId: s.id })}>
            <span className="grow">
              <div className="name">{s.name}</div>
              <div className="meta">{s.duration_varies ? "" : ""}{formatDurationShort(s.duration_min)}{!withHeading && s.description ? ` — ${s.description}` : ""}</div>
            </span>
            <span className="side"><div className="price">{s.price_varies ? "от " : ""}{formatMoney(s.price_minor, tenant.currency)}</div>{withHeading && <div className="choose">Выбрать</div>}</span>
            <ArrowUpRight size={22} aria-hidden />
          </button>
        ))}
        {list.length === 0 && <p className="muted" style={{ padding: 16 }}>Услуги скоро появятся.</p>}
      </div>
    </Reveal>
  );
}

export function SiteFooter() {
  const { tenant } = useStudio();
  const { branding } = tenant;
  return (
    <footer className="page">
      <div className="site-footer">
        <span>{tenant.name}</span>
        {tenant.phone && <a href={telHref(tenant.phone)}>Связаться <ArrowUpRight size={20} aria-hidden /></a>}
      </div>
      {branding.show && (
        <p className="branding">
          Работает на {branding.url ? <a href={branding.url} target="_blank" rel="noopener noreferrer">{branding.name}</a> : branding.name}
        </p>
      )}
    </footer>
  );
}

export function HomeView() {
  const profile = useProfile();
  const has = (k: string) => profile.home.includes(k);
  return (
    <>
      <Hero />
      <Facts />
      <DayPills />
      {has("masters") && <Masters />}
      <ServiceList limit={6} />
      {has("works") && <WorksReel />}
      <Visit />
      {has("install") && <InstallCard />}
      <SiteFooter />
    </>
  );
}
