import type { Metadata } from "next";
import Image from "next/image";
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

function Phone({ src, alt, priority = false }: { src: string; alt: string; priority?: boolean }) {
  return (
    <div className="ph">
      <Image src={src} alt={alt} width={585} height={1266} sizes="(max-width: 700px) 70vw, 300px" priority={priority} />
    </div>
  );
}

const CLIENT = [
  { src: S("c-home"), title: "Страница вашего сервиса", text: "Услуги, цены, адрес и часы работы. Ссылку ставите в соцсети, на карты и на визитку." },
  { src: S("c-book-3"), title: "Свободное время", text: "Клиент видит только реально свободные окна. Две записи на одно время не попадут." },
  { src: S("c-done"), title: "Запись подтверждена", text: "Сразу, без звонка. Клиент добавляет её в календарь и включает напоминание." },
  { src: S("c-assistant"), title: "Помощник", text: "«Полировка фар в пятницу утром» — и он предлагает подходящее время кнопками." },
];

const OWNER = [
  { src: S("o-schedule"), title: "Расписание", text: "Записи на день и неделю, по боксам и мастерам." },
  { src: S("o-booking"), title: "Карточка записи", text: "Позвонить клиенту, перенести, отменить — в одно касание." },
  { src: S("o-assistant"), title: "Помощник владельца", text: "«Что у меня завтра?», «добавь услугу», «суббота выходной»." },
  { src: S("o-services"), title: "Услуги и цены", text: "Меняете сами с телефона, клиенты сразу видят новое." },
];

const KINDS = [
  ["Автосервисы", "боксы и подъёмники, работы на несколько дней, марка и госномер в записи"],
  ["Автомойки и детейлинг", "короткие услуги с шагом 30 минут, запись без звонков в разгар смены"],
  ["Мастера", "личный график и прайс, клиенты не пишут в мессенджер, а сразу занимают окно"],
  ["Салоны и студии", "несколько мастеров со своими часами, клиент выбирает к кому"],
];

const PLANS = [
  { name: "Стандарт", price: "3 500", text: "Страница записи по нашей ссылке, кабинет, приложение на телефон, уведомления, помощник." },
  { name: "Свой домен", price: "4 000", text: "Всё из «Стандарта» на вашем адресе, например book.вашсервис.ru." },
  { name: "Свой сервер", price: "7 000", text: "Приложение и данные на вашем сервере, без нашей подписи на сайте." },
];

const FAQ = [
  ["Нужно платить каждый месяц?", "Нет. Платите один раз за пакет — запись работает бессрочно. Лимитов на записи, боксы и мастеров нет."],
  ["Сколько времени занимает подключение?", "Обычно день. Мы заносим ваши услуги, цены, график и фото, вы получаете ссылку для клиентов и вход в кабинет."],
  ["Клиентам нужно что-то устанавливать?", "Нет, запись работает в браузере. Добавить иконку на экран телефона — по желанию, в одно касание."],
  ["Смогу поменять цены и график сам?", "Да, в кабинете на телефоне. Или напишите помощнику: «подними цену на мойку до 900»."],
  ["Где хранятся данные клиентов?", "На сервере в России. В пакете «Свой сервер» — на вашем."],
];

export default function Landing() {
  return (
    <div className="cl">
      <header className="cl-nav">
        <div className="cl-wrap cl-nav-in">
          <a href="#top" aria-label="clientall — наверх"><Logo size={26} /></a>
          <nav aria-label="Разделы"><a href="#client">Для клиента</a><a href="#owner">Для владельца</a><a href="#prices">Цены</a><a href="#faq">Вопросы</a></nav>
          <a href="#form" className="cl-btn cl-btn-sm">Подключить</a>
        </div>
      </header>

      <main id="top">
        <section className="cl-hero-sec"><div className="cl-hero cl-wrap">
          <div className="cl-hero-copy">
            <h1>Онлайн-запись для автосервиса, мойки и салона</h1>
            <p className="cl-lead">Клиенты сами выбирают услугу и свободное время по ссылке. Вы видите все записи в кабинете на телефоне и получаете уведомление о каждой новой.</p>
            <LeadForm compact />
            <p className="cl-hero-note">3 500 ₽ один раз, без подписки. Запуск за день.</p>
          </div>
          <div className="cl-hero-phones" aria-label="Экраны приложения">
            <Phone src={S("c-book-3")} alt="Клиент выбирает время записи" priority />
            <Phone src={S("o-schedule")} alt="Расписание в кабинете владельца" priority />
          </div>
        </div></section>

        <section id="client" className="cl-sec">
          <div className="cl-wrap">
            <div className="cl-head"><h2>Так записывается ваш клиент</h2><p>Без регистрации, паролей и установки приложения. Ниже — настоящие экраны.</p></div>
          </div>
          <div className="cl-rail cl-wrap">
            {CLIENT.map((s) => (
              <figure key={s.title} className="cl-shot"><Phone src={s.src} alt={s.title} /><figcaption><b>{s.title}</b>{s.text}</figcaption></figure>
            ))}
          </div>
        </section>

        <section id="owner" className="cl-sec cl-bg cl-bg-owner">
          <div className="cl-wrap">
            <div className="cl-head"><h2>А так это видите вы</h2><p>Кабинет открывается с иконки на телефоне. Уведомление о новой записи приходит сразу.</p></div>
          </div>
          <div className="cl-rail cl-wrap">
            {OWNER.map((s) => (
              <figure key={s.title} className="cl-shot"><Phone src={s.src} alt={s.title} /><figcaption><b>{s.title}</b>{s.text}</figcaption></figure>
            ))}
          </div>
        </section>

        <section className="cl-sec cl-wrap cl-kinds-sec">
          <div className="cl-head"><h2>Подходит</h2></div>
          <ul className="cl-kinds">{KINDS.map(([t, d]) => <li key={t}><b>{t}</b><span>{d}</span></li>)}</ul>
        </section>

        <section id="prices" className="cl-sec cl-wrap">
          <div className="cl-head"><h2>Цены</h2><p>Один платёж. Без подписок, процентов и лимитов.</p></div>
          <div className="cl-plans">
            {PLANS.map((p) => (
              <div key={p.name} className="cl-plan">
                <b>{p.name}</b>
                <p>{p.text}</p>
                <span className="cl-price">{p.price}&nbsp;₽</span>
              </div>
            ))}
          </div>
        </section>

        <section id="faq" className="cl-sec cl-wrap">
          <div className="cl-head"><h2>Вопросы</h2></div>
          <div className="cl-faq">{FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div>
        </section>

        <section id="form" className="cl-sec cl-bg cl-bg-form"><div className="cl-wrap cl-form-grid">
          <div className="cl-head">
            <h2>Подключим запись за день</h2>
            <p>Оставьте телефон — перезвоним, спросим про услуги и график и покажем, как будет выглядеть ваша страница. Платить — только если понравится.</p>
          </div>
          <LeadForm />
        </div></section>
      </main>

      <footer className="cl-foot cl-wrap"><Logo size={20} /><span>© {new Date().getFullYear()} · онлайн-запись для сервиса и красоты</span></footer>
    </div>
  );
}
