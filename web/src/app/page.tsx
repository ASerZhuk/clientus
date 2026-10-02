import type { Metadata } from "next";
import Image from "next/image";
import {
  ArrowRight, BellRinging, CalendarCheck, ChatCircleDots, CheckCircle, DeviceMobile, Globe, Lightning, Storefront, UsersThree,
} from "@phosphor-icons/react/dist/ssr";
import { LeadForm } from "@/components/landing/LeadForm";
import "./landing.css";

export const metadata: Metadata = {
  title: "Clientus — онлайн-запись для автосервиса, мойки и салона красоты",
  description: "Свой сайт записи и приложение на телефон для клиентов. Кабинет владельца, уведомления, помощник. Подключение за один день, оплата один раз — без подписки.",
  robots: { index: true, follow: true },
};

const KINDS = [
  { img: "/landing/auto.webp", title: "Автосервис", text: "Боксы и подъёмники, длительные работы, марка и госномер в записи." },
  { img: "/landing/wash.webp", title: "Автомойка", text: "Короткие услуги с шагом 30 минут, быстрая запись без звонков." },
  { img: "/landing/master.webp", title: "Мастер красоты", text: "Личное расписание, услуги и цены, клиенты записываются сами." },
  { img: "/landing/studio.webp", title: "Студия красоты", text: "Несколько мастеров со своим графиком — клиент выбирает, к кому." },
];

const FEATURES = [
  { Icon: CalendarCheck, title: "Запись без звонков", text: "Клиент выбирает услугу и свободное время сам — без регистрации и паролей." },
  { Icon: DeviceMobile, title: "Приложение на телефон", text: "Сайт ставится иконкой на экран клиента и владельца, как обычное приложение." },
  { Icon: BellRinging, title: "Уведомления", text: "Вам — о новой записи и отмене, клиенту — напоминание перед визитом." },
  { Icon: ChatCircleDots, title: "Помощник", text: "Подбирает клиенту время по фразе «развал в субботу утром». Вам — меняет цены и график по команде." },
  { Icon: UsersThree, title: "Боксы и мастера", text: "Несколько рабочих мест, своё расписание у каждого, никаких двойных записей." },
  { Icon: Globe, title: "Свой адрес", text: "Работает по нашей ссылке или на вашем домене — например, book.вашсервис.ru." },
];

const PLANS = [
  { name: "Стандарт", price: "3 500 ₽", text: "Сайт записи по нашей ссылке, кабинет владельца, приложение, уведомления, помощник.", accent: false },
  { name: "Свой домен", price: "4 000 ₽", text: "Всё из «Стандарта» на вашем адресе: book.вашсервис.ru. HTTPS настроим автоматически.", accent: true },
  { name: "Свой сервер", price: "7 000 ₽", text: "Приложение и данные на вашем сервере, без нашей подписи внизу сайта.", accent: false },
];

const FAQ = [
  { q: "Нужно платить каждый месяц?", a: "Нет. Оплата один раз за пакет, студия работает бессрочно. Лимитов на записи, боксы и мастеров нет." },
  { q: "Сколько времени занимает подключение?", a: "Обычно один день: мы заносим ваши услуги, цены, график и фото, вы получаете ссылку для клиентов и вход в кабинет." },
  { q: "Клиентам нужно что-то устанавливать?", a: "Нет. Запись работает по ссылке в браузере. По желанию клиент добавит иконку на экран телефона в одно касание." },
  { q: "Можно поменять цены и график самому?", a: "Да, в кабинете на телефоне — или просто напишите помощнику: «подними цену на мойку до 900»." },
  { q: "Где хранятся данные?", a: "На сервере в России. В пакете «Свой сервер» — на вашем." },
];

export default function Landing() {
  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-wrap lp-nav-inner">
          <a href="#top" className="lp-brand" aria-label="Clientus — наверх"><span className="lp-brand-mark" aria-hidden><Lightning weight="fill" /></span>Clientus</a>
          <nav className="lp-links" aria-label="Разделы">
            <a href="#for">Для кого</a><a href="#features">Возможности</a><a href="#prices">Цены</a><a href="#faq">Вопросы</a>
          </nav>
          <a href="#form" className="lp-btn lp-btn-sm">Подключить</a>
        </div>
      </header>

      <main id="top">
        <section className="lp-hero">
          <div className="lp-wrap lp-hero-grid">
            <div className="lp-hero-copy">
              <span className="lp-eyebrow"><span className="lp-dot" aria-hidden />Без подписки · запуск за 1 день</span>
              <h1>Онлайн-запись, которая работает, пока вы работаете</h1>
              <p className="lp-lead">Свой сайт записи и приложение на телефон для автосервиса, мойки и салона красоты. Клиенты записываются сами — вы видите всё в кабинете и получаете уведомления.</p>
              <div className="lp-cta-row">
                <a href="#form" className="lp-btn">Подключить запись <ArrowRight weight="bold" aria-hidden /></a>
                <a href="#how" className="lp-btn lp-btn-ghost">Как это работает</a>
              </div>
              <ul className="lp-trust">
                <li><CheckCircle weight="fill" aria-hidden />от 3 500 ₽ один раз</li>
                <li><CheckCircle weight="fill" aria-hidden />без лимитов на записи</li>
                <li><CheckCircle weight="fill" aria-hidden />данные в России</li>
              </ul>
            </div>
            <div className="lp-hero-art">
              <Image src="/landing/hero.webp" alt="Клиент записывается на сервис с телефона" fill priority sizes="(max-width: 900px) 100vw, 50vw" />
              <div className="lp-float lp-float-a"><BellRinging weight="fill" aria-hidden /><span><b>Новая запись</b><small>сб, 10:00 · Развал-схождение</small></span></div>
              <div className="lp-float lp-float-b"><CalendarCheck weight="fill" aria-hidden /><span><b>Свободно</b><small>11:00 · 12:00 · 14:30</small></span></div>
            </div>
          </div>
        </section>

        <section id="for" className="lp-section">
          <div className="lp-wrap">
            <h2>Для кого</h2>
            <p className="lp-sub">Одна система, настроенная под ваш бизнес: свои слова, поля и правила записи.</p>
            <div className="lp-kinds">
              {KINDS.map((k) => (
                <article key={k.title} className="lp-kind">
                  <Image src={k.img} alt="" fill sizes="(max-width: 700px) 80vw, 25vw" />
                  <div className="lp-kind-text"><h3>{k.title}</h3><p>{k.text}</p></div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="how" className="lp-section">
          <div className="lp-wrap lp-how">
            <div>
              <h2>Как это работает</h2>
              <p className="lp-sub">Клиенту — три касания. Вам — запись в кабинете и уведомление на телефон.</p>
            </div>
            <ol className="lp-steps">
              <li><b>Клиент открывает вашу ссылку</b><span>Из соцсетей, карт, визитки или QR-кода на стойке.</span></li>
              <li><b>Выбирает услугу и время</b><span>Видит только реально свободные окна — двойных записей не бывает.</span></li>
              <li><b>Оставляет имя и телефон</b><span>Запись подтверждена сразу, перед визитом придёт напоминание.</span></li>
              <li><b>Вы получаете уведомление</b><span>Запись уже в расписании кабинета: перенос, отмена, звонок клиенту — в одно касание.</span></li>
            </ol>
          </div>
        </section>

        <section id="features" className="lp-section">
          <div className="lp-wrap">
            <h2>Возможности</h2>
            <div className="lp-features">
              {FEATURES.map(({ Icon, title, text }) => (
                <article key={title} className="lp-feature"><span className="lp-icon" aria-hidden><Icon weight="duotone" /></span><h3>{title}</h3><p>{text}</p></article>
              ))}
            </div>
          </div>
        </section>

        <section id="prices" className="lp-section">
          <div className="lp-wrap">
            <h2>Цены</h2>
            <p className="lp-sub">Платите один раз. Никаких подписок, процентов и лимитов.</p>
            <div className="lp-plans">
              {PLANS.map((p) => (
                <article key={p.name} className={`lp-plan${p.accent ? " lp-plan-accent" : ""}`}>
                  {p.accent && <span className="lp-badge">Популярный</span>}
                  <h3>{p.name}</h3>
                  <div className="lp-price">{p.price}<small> один раз</small></div>
                  <p>{p.text}</p>
                  <a href="#form" className={`lp-btn ${p.accent ? "" : "lp-btn-ghost"}`}>Выбрать</a>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="faq" className="lp-section">
          <div className="lp-wrap lp-faq-wrap">
            <h2>Вопросы</h2>
            <div className="lp-faq">
              {FAQ.map((f) => <details key={f.q}><summary>{f.q}</summary><p>{f.a}</p></details>)}
            </div>
          </div>
        </section>

        <section id="form" className="lp-section lp-form-section">
          <div className="lp-wrap lp-form-grid">
            <div>
              <span className="lp-icon lp-icon-lg" aria-hidden><Storefront weight="duotone" /></span>
              <h2>Подключить онлайн-запись</h2>
              <p className="lp-sub">Оставьте контакты — перезвоним в течение дня, уточним услуги и график и пришлём готовую ссылку для клиентов.</p>
              <ul className="lp-trust lp-trust-col">
                <li><CheckCircle weight="fill" aria-hidden />Бесплатно покажем, как будет выглядеть ваша запись</li>
                <li><CheckCircle weight="fill" aria-hidden />Оплата только после того, как понравится</li>
                <li><CheckCircle weight="fill" aria-hidden />Настроим всё за вас</li>
              </ul>
            </div>
            <LeadForm />
          </div>
        </section>
      </main>

      <footer className="lp-footer"><div className="lp-wrap">© {new Date().getFullYear()} Clientus · онлайн-запись для сервиса и красоты</div></footer>
    </div>
  );
}
