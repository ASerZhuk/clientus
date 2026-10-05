import type { Metadata } from "next";
import Image from "next/image";
import {
  ArrowRight, BellRinging, CalendarCheck, CarProfile, ChatCircleDots, Check, Clock, Drop, Infinity as InfinityIcon, Lightning, PaintBrush, Scissors,
  Sparkle, Storefront, Wallet, Wrench,
} from "@phosphor-icons/react/dist/ssr";
import { LeadForm } from "@/components/landing/LeadForm";
import { Logo } from "@/components/landing/Logo";
import "./landing.css";

export const metadata: Metadata = {
  title: "clientall — онлайн-запись для автосервиса, мойки и салона",
  description: "Клиенты записываются сами по ссылке, вы видите записи в кабинете на телефоне и получаете уведомления. Подключение за день, оплата один раз — без подписки.",
  robots: { index: true, follow: true },
  icons: { icon: "/brand/clientall-mark.svg" },
};

const S = (n: string) => `/landing/screens/${n}.webp`;

function Phone({ src, alt, priority = false, className = "" }: { src: string; alt: string; priority?: boolean; className?: string }) {
  return (
    <div className={`ph ${className}`}>
      <Image src={src} alt={alt} width={585} height={1266} sizes="(max-width: 700px) 60vw, 300px" priority={priority} />
    </div>
  );
}

const FACTS = [
  { Icon: Clock, big: "24/7", small: "онлайн-запись" },
  { Icon: Lightning, big: "1 день", small: "на подключение" },
  { Icon: Wallet, big: "0 ₽", small: "комиссии с записей" },
  { Icon: InfinityIcon, big: "Без лимитов", small: "записей, боксов и мастеров" },
];

const KINDS = [
  { Icon: Wrench, title: "Автосервисы", text: "Боксы, подъёмники, работы на несколько дней" },
  { Icon: Drop, title: "Автомойки", text: "Короткие услуги с шагом 30 минут" },
  { Icon: CarProfile, title: "Детейлинг", text: "Полировка, керамика, химчистка" },
  { Icon: PaintBrush, title: "Мастера красоты", text: "Маникюр, брови, ресницы, визаж" },
  { Icon: Scissors, title: "Салоны и барбершопы", text: "Несколько мастеров со своим графиком" },
];

const PLANS = [
  { name: "Стандарт", note: "Для одного сервиса", price: "3 500", points: ["Страница записи по нашей ссылке", "Кабинет владельца на телефоне", "Уведомления и помощник"], hot: false },
  { name: "Свой домен", note: "Ваш адрес вместо нашего", price: "4 000", points: ["Всё из «Стандарта»", "Адрес вида book.вашсервис.ru", "HTTPS настроим сами"], hot: true },
  { name: "Свой сервер", note: "Данные у вас", price: "7 000", points: ["Всё из «Своего домена»", "Установка на ваш сервер", "Без нашей подписи на сайте"], hot: false },
];

const FAQ = [
  ["Нужно платить каждый месяц?", "Нет. Платите один раз за пакет — запись работает бессрочно. Лимитов на записи, боксы и мастеров нет."],
  ["Клиентам нужно устанавливать приложение?", "Нет, запись работает в браузере по ссылке. Добавить иконку на экран телефона — по желанию, в одно касание."],
  ["Как работают уведомления?", "Вам приходит уведомление о новой записи, переносе и отмене. Клиенту — напоминание перед визитом, если он его включил."],
  ["Подходит ли для нескольких боксов или мастеров?", "Да. У каждого бокса или мастера своё расписание и выходные, двойных записей не бывает."],
  ["Сколько времени занимает подключение?", "Обычно день. Мы заносим ваши услуги, цены, график и фото, вы получаете ссылку для клиентов и вход в кабинет."],
];

export default function Landing() {
  return (
    <div className="cl">
      <header className="cl-nav">
        <div className="cl-wrap cl-nav-in">
          <a href="#top" aria-label="clientall — наверх"><Logo size={26} accent="#121212" /></a>
          <nav aria-label="Разделы"><a href="#features">Возможности</a><a href="#how">Как это работает</a><a href="#prices">Тарифы</a><a href="#for">Для кого</a></nav>
          <a href="#form" className="cl-btn cl-btn-sm">Подключить <ArrowRight weight="bold" aria-hidden /></a>
        </div>
      </header>

      <main id="top">
        <section className="cl-hero cl-wrap">
          <div className="cl-hero-copy">
            <p className="cl-eyebrow">Онлайн-запись для бизнеса</p>
            <h1>Запись, которая работает <mark>сама</mark></h1>
            <p className="cl-lead">Клиенты записываются без звонков и переписок. Вы видите все записи в телефоне и получаете уведомление о каждой новой.</p>
            <div className="cl-cta">
              <a href="#form" className="cl-btn">Подключить запись <ArrowRight weight="bold" aria-hidden /></a>
              <a href="#how" className="cl-btn cl-btn-ghost">Как это работает</a>
            </div>
            <p className="cl-hero-note">3 500 ₽ один раз · Без подписки · Запуск за день</p>
          </div>
          <div className="cl-hero-art">
            <Phone src={S("o-schedule")} alt="Расписание в кабинете владельца" priority className="ph-a" />
            <Phone src={S("c-book-3")} alt="Клиент выбирает время" priority className="ph-b" />
            <div className="cl-toast t1"><span className="cl-ico"><CalendarCheck weight="duotone" /></span><span><b>Новая запись</b>Дмитрий · 5 октября, 11:00</span></div>
            <div className="cl-toast t2"><span className="cl-ico"><BellRinging weight="duotone" /></span><span><b>Напоминание отправлено</b>Сергей · завтра в 17:00</span></div>
            <div className="cl-toast t3"><span className="cl-ico"><ChatCircleDots weight="duotone" /></span><span><b>Помощник</b>«Суббота выходной» — готово</span></div>
          </div>
        </section>

        <section className="cl-wrap" aria-label="Коротко">
          <ul className="cl-facts">
            {FACTS.map(({ Icon, big, small }) => <li key={big}><span className="cl-ico"><Icon weight="duotone" /></span><span><b>{big}</b>{small}</span></li>)}
          </ul>
        </section>

        <section id="features" className="cl-sec cl-wrap">
          <p className="cl-eyebrow">Возможности</p>
          <h2>Всё, что нужно для <mark>онлайн-записи</mark></h2>
          <div className="cl-feats">
            <article className="cl-feat">
              <span className="cl-ico"><Storefront weight="duotone" /></span>
              <h3>Онлайн-запись</h3><p>Клиент выбирает услугу и время в пару касаний — круглосуточно.</p>
              <div className="mini">
                <small>Выберите услугу</small>
                <div className="mini-row"><span><b>Премиум мойка</b>2 ч · 3 500 ₽</span><ArrowRight aria-hidden /></div>
                <div className="mini-row"><span><b>Полировка фар</b>1,5 ч · 3 500 ₽</span><ArrowRight aria-hidden /></div>
              </div>
            </article>
            <article className="cl-feat">
              <span className="cl-ico"><CalendarCheck weight="duotone" /></span>
              <h3>Умное расписание</h3><p>Свободные окна считаются сами по боксам и мастерам. Двойных записей нет.</p>
              <div className="mini mini-slots">
                <span>10:00</span><span className="busy">11:00</span><span className="on">12:00</span><span>13:30</span><span className="busy">14:00</span><span>15:00</span>
              </div>
            </article>
            <article className="cl-feat">
              <span className="cl-ico"><Sparkle weight="duotone" /></span>
              <h3>Помощник</h3><p>Отвечает клиентам и выполняет ваши команды: цены, график, новые записи.</p>
              <div className="mini mini-chat">
                <span className="me">Добавь услугу «Замена масла», 1500 ₽, 20 мин</span>
                <span className="bot">Готово: «Замена масла» — 1 500 ₽, 20 мин.</span>
              </div>
            </article>
            <article className="cl-feat">
              <span className="cl-ico"><BellRinging weight="duotone" /></span>
              <h3>Уведомления</h3><p>Вам — о каждой записи. Клиенту — напоминание перед визитом.</p>
              <div className="mini">
                {["Новая запись", "Перенос и отмена", "Напоминание клиенту за 24 ч"].map((t) => <div key={t} className="mini-toggle"><span>{t}</span><i aria-hidden /></div>)}
              </div>
            </article>
          </div>
        </section>

        <section className="cl-sec cl-tint">
          <div className="cl-wrap cl-split">
            <div className="cl-split-text">
              <p className="cl-eyebrow">Управляйте бизнесом</p>
              <h2>Всё расписание под&nbsp;контролем</h2>
              <p className="cl-lead">Записи на день и неделю по каждому боксу или мастеру. Позвонить клиенту, перенести или отменить запись — в одно касание.</p>
              <ul className="cl-checks"><li><Check weight="bold" aria-hidden />Кабинет открывается с иконки на телефоне</li><li><Check weight="bold" aria-hidden />Услуги и цены меняете сами</li><li><Check weight="bold" aria-hidden />Помощник ответит, что у вас завтра</li></ul>
              <a href="#form" className="cl-btn">Подключить запись <ArrowRight weight="bold" aria-hidden /></a>
            </div>
            <div className="cl-split-art cl-duo">
              <Phone src={S("o-booking")} alt="Карточка записи" />
              <Phone src={S("o-assistant")} alt="Помощник владельца" />
            </div>
          </div>
        </section>

        <section id="how" className="cl-sec">
          <div className="cl-wrap cl-split cl-split-rev">
            <div className="cl-split-text">
              <p className="cl-eyebrow">Для ваших клиентов</p>
              <h2>Клиент записывается <mark>за минуту</mark></h2>
              <p className="cl-lead">Открывает вашу ссылку из карт, соцсетей или QR-кода, выбирает услугу и время, оставляет имя и телефон. Без регистрации и звонков.</p>
            </div>
            <div className="cl-split-art cl-fan">
              <Phone src={S("c-home")} alt="Страница сервиса" />
              <Phone src={S("c-book-3")} alt="Выбор времени" />
              <Phone src={S("c-done")} alt="Запись подтверждена" />
            </div>
          </div>
        </section>

        <section id="for" className="cl-sec cl-wrap">
          <p className="cl-eyebrow">Для кого подходит</p>
          <h2>Для любого бизнеса, <mark>где есть запись</mark></h2>
          <div className="cl-kinds">{KINDS.map(({ Icon, title, text }) => <div key={title} className="cl-kind"><span className="cl-ico"><Icon weight="duotone" /></span><span><b>{title}</b>{text}</span></div>)}</div>
        </section>

        <section id="prices" className="cl-sec cl-wrap">
          <p className="cl-eyebrow">Простые тарифы</p>
          <h2>Один платёж — и запись ваша</h2>
          <div className="cl-plans">
            {PLANS.map((p) => (
              <div key={p.name} className={`cl-plan${p.hot ? " hot" : ""}`}>
                {p.hot && <span className="cl-badge">Популярный</span>}
                <b>{p.name}</b><small>{p.note}</small>
                <div className="cl-price">{p.price} ₽<small>один раз</small></div>
                <ul>{p.points.map((x) => <li key={x}><Check weight="bold" aria-hidden />{x}</li>)}</ul>
                <a href="#form" className={`cl-btn ${p.hot ? "" : "cl-btn-ghost"} cl-btn-block`}>Оставить заявку</a>
              </div>
            ))}
          </div>
        </section>

        <section className="cl-sec cl-wrap cl-faq-grid">
          <div><p className="cl-eyebrow">Остались вопросы?</p><h2>Часто спрашивают</h2><a href="#form" className="cl-btn cl-btn-ghost cl-btn-sm">Задать свой вопрос <ArrowRight weight="bold" aria-hidden /></a></div>
          <div className="cl-faq">{FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div>
        </section>

        <section id="form" className="cl-wrap">
          <div className="cl-final">
            <div>
              <h2>Начните уже сегодня</h2>
              <p>Оставьте телефон — перезвоним, уточним услуги и график и пришлём ссылку на вашу страницу записи. Платите, только если понравится.</p>
            </div>
            <LeadForm />
          </div>
        </section>
      </main>

      <footer className="cl-foot cl-wrap">
        <Logo size={22} accent="#121212" />
        <span>Онлайн-запись, которая работает сама</span>
        <nav aria-label="Ссылки"><a href="#features">Возможности</a><a href="#prices">Тарифы</a><a href="#for">Для кого</a></nav>
      </footer>
    </div>
  );
}
