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

function Phone({ src, alt, priority = false, className = "" }: { src: string; alt: string; priority?: boolean; className?: string }) {
  return (
    <div className={`ph ${className}`}>
      <Image src={src} alt={alt} width={585} height={1266} sizes="(max-width: 700px) 72vw, 320px" priority={priority} />
    </div>
  );
}

const STEPS = [
  { src: S("c-home"), title: "Открывает вашу ссылку", text: "Из Яндекс Карт, 2ГИС, соцсетей или QR-кода на стойке. Видит услуги, цены и адрес." },
  { src: S("c-book-3"), title: "Выбирает время", text: "Показываем только свободные окна с учётом боксов и длительности работ." },
  { src: S("c-done"), title: "Получает подтверждение", text: "Сразу, без звонка. Перед визитом приходит напоминание на телефон." },
];

const OWNER = [
  {
    src: S("o-schedule"), title: "Все записи — в телефоне",
    points: ["Расписание на день и неделю по каждому боксу или мастеру", "Уведомление о новой записи, переносе и отмене", "Позвонить клиенту или перенести запись в одно касание"],
  },
  {
    src: S("o-assistant"), title: "Помощник делает рутину за вас",
    points: ["«Что у меня завтра?» — список записей за секунду", "«Добавь услугу замена масла 1500 ₽ 20 минут» — и она уже в прайсе", "«В субботу выходной» — график обновлён"],
  },
];

const KINDS = [
  { title: "Автосервис", text: "Боксы и подъёмники, работы на несколько дней, марка и госномер в записи." },
  { title: "Автомойка и детейлинг", text: "Короткие услуги с шагом 30 минут, клиенты не звонят в разгар смены." },
  { title: "Мастер красоты", text: "Личный график и прайс. Клиенты не пишут в мессенджер, а сразу занимают окно." },
  { title: "Салон и студия", text: "Несколько мастеров со своими часами. Клиент выбирает к кому или «любой свободный»." },
];

const PLANS = [
  { name: "Стандарт", price: "3 500", text: "Страница записи по нашей ссылке, кабинет, приложение на телефон, уведомления, помощник.", hot: false },
  { name: "Свой домен", price: "4 000", text: "Всё из «Стандарта» на вашем адресе — например, book.вашсервис.ru.", hot: true },
  { name: "Свой сервер", price: "7 000", text: "Приложение и данные на вашем сервере, без нашей подписи на сайте.", hot: false },
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
          <a href="#top" aria-label="clientall — наверх"><Logo size={26} accent="#121212" /></a>
          <nav aria-label="Разделы"><a href="#how">Как работает</a><a href="#owner">Кабинет</a><a href="#prices">Цены</a><a href="#faq">Вопросы</a></nav>
          <a href="#form" className="cl-btn cl-btn-dark cl-btn-sm">Подключить</a>
        </div>
      </header>

      <main id="top">
        <section className="cl-hero cl-wrap">
          <div className="cl-hero-copy">
            <p className="cl-eyebrow">Для автосервисов, моек и салонов</p>
            <h1>Клиенты записываются сами, без&nbsp;звонков</h1>
            <p className="cl-lead">Своя страница онлайн-записи и кабинет на телефоне. Клиент выбирает услугу и свободное время, вам приходит уведомление.</p>
            <LeadForm compact />
            <ul className="cl-facts">
              <li><b>3 500 ₽</b><span>один раз, без подписки</span></li>
              <li><b>1 день</b><span>на подключение</span></li>
              <li><b>0 ₽</b><span>за каждую запись</span></li>
            </ul>
          </div>
          <div className="cl-hero-art">
            <Phone src={S("c-book-3")} alt="Клиент выбирает время записи" priority className="ph-main" />
            <Phone src={S("o-schedule")} alt="Расписание в кабинете владельца" priority className="ph-side" />
          </div>
        </section>

        <section id="how" className="cl-band">
          <div className="cl-wrap">
            <h2>Запись за три шага — без регистрации и звонков</h2>
            <ol className="cl-steps">
              {STEPS.map((s, i) => (
                <li key={s.title}>
                  <Phone src={s.src} alt={s.title} />
                  <div><span className="cl-step-n">{i + 1}</span><b>{s.title}</b><p>{s.text}</p></div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="owner" className="cl-sec cl-wrap">
          <h2 className="cl-h2">Кабинет владельца</h2>
          {OWNER.map((o, i) => (
            <div key={o.title} className={`cl-split${i % 2 ? " cl-split-rev" : ""}`}>
              <Phone src={o.src} alt={o.title} />
              <div className="cl-split-text">
                <h3>{o.title}</h3>
                <ul>{o.points.map((p) => <li key={p}>{p}</li>)}</ul>
              </div>
            </div>
          ))}
        </section>

        <section className="cl-sec cl-wrap">
          <h2 className="cl-h2">Подходит для</h2>
          <div className="cl-kinds">{KINDS.map((k) => <div key={k.title} className="cl-kind"><b>{k.title}</b><p>{k.text}</p></div>)}</div>
        </section>

        <section id="prices" className="cl-sec cl-wrap">
          <h2 className="cl-h2">Цены</h2>
          <p className="cl-sub">Один платёж. Без подписки, процентов с записей и лимитов.</p>
          <div className="cl-plans">
            {PLANS.map((p) => (
              <div key={p.name} className={`cl-plan${p.hot ? " cl-plan-hot" : ""}`}>
                <b>{p.name}</b>
                <span className="cl-price">{p.price}&nbsp;₽</span>
                <p>{p.text}</p>
                <a href="#form" className={`cl-btn ${p.hot ? "" : "cl-btn-dark"}`}>Оставить заявку</a>
              </div>
            ))}
          </div>
        </section>

        <section id="faq" className="cl-sec cl-wrap">
          <h2 className="cl-h2">Вопросы</h2>
          <div className="cl-faq">{FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div>
        </section>

        <section id="form" className="cl-band cl-band-form">
          <div className="cl-wrap cl-form-grid">
            <div>
              <h2>Подключим запись за день</h2>
              <p>Оставьте телефон — перезвоним, уточним услуги и график и пришлём ссылку на вашу страницу записи. Платите, только если понравится.</p>
            </div>
            <LeadForm />
          </div>
        </section>
      </main>

      <footer className="cl-foot cl-wrap"><Logo size={20} accent="#121212" /><span>© {new Date().getFullYear()} clientall · онлайн-запись для сервиса и красоты</span></footer>
    </div>
  );
}
