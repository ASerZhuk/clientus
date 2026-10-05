import type { Metadata } from "next";
import Image from "next/image";
import "@fontsource-variable/onest/index.css";
import "@fontsource/lora/cyrillic-400-italic.css";
import "@fontsource/lora/latin-400-italic.css";
import { LeadForm } from "@/components/landing/LeadForm";
import { Logo, LogoMark } from "@/components/landing/Logo";
import "./landing.css";

export const metadata: Metadata = {
  title: "clientall — онлайн-запись для автосервиса, мойки и салона",
  description: "Клиенты записываются сами по ссылке, вы видите записи в кабинете на телефоне и получаете уведомления. Подключение за день, оплата один раз — без подписки.",
  robots: { index: true, follow: true },
  icons: { icon: "/brand/clientall-mark.svg" },
};

const KINDS = [
  { img: "/landing/auto.webp", title: "Автосервис", text: "Боксы и подъёмники, работы на несколько дней, марка и госномер в записи." },
  { img: "/landing/wash.webp", title: "Автомойка", text: "Короткие услуги, шаг 30 минут, запись без звонков в разгар смены." },
  { img: "/landing/master.webp", title: "Мастер", text: "Личный график и прайс. Клиенты пишут не вам в мессенджер, а сразу в свободное окно." },
  { img: "/landing/studio.webp", title: "Студия", text: "Несколько мастеров, у каждого свои часы. Клиент выбирает к кому или «любой свободный»." },
];

const BEFORE_AFTER = [
  ["Телефон звонит, пока вы под машиной или с клиентом", "Клиент сам выбирает свободное время по ссылке"],
  ["Запись в тетради или в заметках, путаница с боксами", "Расписание по боксам и мастерам, без двойных записей"],
  ["Клиент забыл и не пришёл", "Напоминание приходит ему на телефон перед визитом"],
  ["Цены и время — в голове у одного человека", "Услуги, цены и график в кабинете, меняются за минуту"],
];

const FEATURES = [
  ["Запись без регистрации", "Клиенту не нужны пароль и приложение из магазина — только ссылка."],
  ["Иконка на телефоне", "Сайт ставится на экран клиента и владельца как обычное приложение."],
  ["Уведомления", "Новая запись, перенос, отмена — сразу вам на телефон."],
  ["Помощник", "Клиенту подбирает время по фразе «развал в субботу утром». Вам меняет цены и график по команде."],
  ["Боксы и мастера", "У каждого свой график и выходные. Свободные окна считаются сами."],
  ["Ваш адрес", "По нашей ссылке или на вашем домене — book.вашсервис.ru."],
];

const PLANS = [
  { name: "Стандарт", price: "3 500", text: "Сайт записи по нашей ссылке, кабинет, приложение, уведомления, помощник." },
  { name: "Свой домен", price: "4 000", text: "Всё из «Стандарта» на вашем адресе. HTTPS настроим сами." },
  { name: "Свой сервер", price: "7 000", text: "Приложение и данные на вашем сервере, без нашей подписи на сайте." },
];

const FAQ = [
  ["Нужно платить каждый месяц?", "Нет. Платите один раз за пакет — запись работает бессрочно. Лимитов на записи, боксы и мастеров нет."],
  ["Сколько времени занимает подключение?", "Обычно день. Мы заносим ваши услуги, цены, график и фото, вы получаете ссылку для клиентов и вход в кабинет."],
  ["Клиентам нужно что-то устанавливать?", "Нет, запись работает в браузере. Добавить иконку на экран — по желанию, в одно касание."],
  ["Смогу поменять цены и график сам?", "Да, в кабинете на телефоне. Или напишите помощнику: «подними цену на мойку до 900»."],
  ["Где хранятся данные клиентов?", "На сервере в России. В пакете «Свой сервер» — на вашем."],
];

function BookingMock() {
  const slots = [["10:00", ""], ["11:00", "busy"], ["12:00", "on"], ["13:30", ""], ["14:00", "busy"], ["15:00", ""]];
  return (
    <div className="mk" aria-hidden>
      <div className="mk-phone">
        <div className="mk-top"><span className="mk-ava">К</span><span><b>Колесо</b><small>автосервис · Волгоград</small></span></div>
        <p className="mk-label">Развал-схождение · 1 час · 2 000 ₽</p>
        <div className="mk-days">
          {[["пн", "6"], ["вт", "7"], ["ср", "8"], ["чт", "9"], ["пт", "10"]].map(([d, n], i) => <span key={n} className={i === 1 ? "on" : ""}><small>{d}</small>{n}</span>)}
        </div>
        <div className="mk-slots">{slots.map(([t, s]) => <span key={t} className={s}>{t}</span>)}</div>
        <div className="mk-btn">Записаться на 12:00</div>
      </div>
      <div className="mk-push">
        <LogoMark size={22} />
        <span><b>Новая запись</b>вт, 7 октября, 12:00 · Развал-схождение · Kia Rio</span>
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <div className="cl">
      <a href="#form" className="cl-skip">К заявке</a>
      <header className="cl-nav">
        <div className="cl-wrap cl-nav-in">
          <a href="#top" aria-label="clientall — наверх"><Logo size={28} /></a>
          <nav aria-label="Разделы"><a href="#for">Для кого</a><a href="#prices">Цены</a><a href="#faq">Вопросы</a></nav>
          <a href="#form" className="cl-btn cl-btn-sm">Оставить заявку</a>
        </div>
      </header>

      <main id="top">
        <section className="cl-hero cl-wrap">
          <div className="cl-hero-copy">
            <p className="cl-kicker">Онлайн-запись для сервиса и красоты</p>
            <h1>Клиенты записываются сами. <em>Вы&nbsp;— работаете.</em></h1>
            <p className="cl-lead">Своя страница записи и приложение на телефон. Клиент выбирает услугу и свободное время, вы получаете уведомление и видите запись в кабинете.</p>
            <div className="cl-cta">
              <a href="#form" className="cl-btn">Подключить за 3 500 ₽</a>
              <span className="cl-cta-note">один раз, без подписки<br />запуск за день</span>
            </div>
          </div>
          <BookingMock />
        </section>

        <section id="for" className="cl-sec cl-wrap">
          <div className="cl-head"><span className="cl-num">01</span><h2>Для кого</h2></div>
          <div className="cl-kinds">
            {KINDS.map((k) => (
              <figure key={k.title} className="cl-kind">
                <div className="cl-kind-img"><Image src={k.img} alt={k.title} fill sizes="(max-width: 700px) 50vw, 25vw" /></div>
                <figcaption><b>{k.title}</b>{k.text}</figcaption>
              </figure>
            ))}
          </div>
        </section>

        <section className="cl-sec cl-wrap">
          <div className="cl-head"><span className="cl-num">02</span><h2>Что изменится</h2></div>
          <div className="cl-ba" role="table" aria-label="Было и стало">
            <div className="cl-ba-row cl-ba-th" role="row"><span role="columnheader">Было</span><span role="columnheader">С clientall</span></div>
            {BEFORE_AFTER.map(([a, b]) => <div key={a} className="cl-ba-row" role="row"><span role="cell">{a}</span><span role="cell">{b}</span></div>)}
          </div>
        </section>

        <section className="cl-sec cl-wrap">
          <div className="cl-head"><span className="cl-num">03</span><h2>Что внутри</h2></div>
          <dl className="cl-feat">
            {FEATURES.map(([t, d]) => <div key={t}><dt>{t}</dt><dd>{d}</dd></div>)}
          </dl>
        </section>

        <section id="prices" className="cl-sec cl-wrap">
          <div className="cl-head"><span className="cl-num">04</span><h2>Цены</h2><p>Один платёж. Без подписок, процентов и лимитов.</p></div>
          <div className="cl-plans">
            {PLANS.map((p) => (
              <div key={p.name} className="cl-plan">
                <b>{p.name}</b>
                <p>{p.text}</p>
                <span className="cl-price">{p.price}&nbsp;₽</span>
                <a href="#form" className="cl-btn cl-btn-line cl-btn-sm">Выбрать</a>
              </div>
            ))}
          </div>
        </section>

        <section id="faq" className="cl-sec cl-wrap">
          <div className="cl-head"><span className="cl-num">05</span><h2>Вопросы</h2></div>
          <div className="cl-faq">{FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div>
        </section>

        <section id="form" className="cl-form-sec">
          <div className="cl-wrap cl-form-grid">
            <div className="cl-form-copy">
              <h2>Подключим запись <em>за&nbsp;день</em></h2>
              <p>Оставьте телефон — перезвоним, спросим про услуги и график и покажем, как будет выглядеть ваша страница. Платить — только если понравится.</p>
            </div>
            <LeadForm />
          </div>
        </section>
      </main>

      <footer className="cl-foot cl-wrap"><Logo size={22} /><span>© {new Date().getFullYear()} · онлайн-запись для сервиса и красоты</span></footer>
    </div>
  );
}
