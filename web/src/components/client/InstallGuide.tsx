"use client";

import { SegmentedControl, SegmentedControlItem } from "@/components/ui/Pill";
import { useEffect, useState } from "react";
import { useStudio } from "@/components/StudioProviders";
import { useInstall } from "@/lib/install";

type Platform = "ios" | "android" | "desktop";

const STEPS: Record<Platform, { title: string; text: string }[]> = {
  ios: [
    { title: "Откройте «Поделиться»", text: "Откройте сайт в Safari. Нажмите квадрат со стрелкой вверх. В некоторых версиях Safari он находится в меню «…»." },
    { title: "Выберите «На экран Домой»", text: "Прокрутите список действий вниз. Если пункта нет, найдите его через «Ещё»." },
    { title: "Нажмите «Добавить»", text: "Иконка студии появится на главном экране и будет открываться без адресной строки." },
  ],
  android: [
    { title: "Откройте меню браузера", text: "В Chrome нажмите «⋮» в правом верхнем углу." },
    { title: "Выберите «Установить приложение»", text: "Или «Добавить на главный экран», если установка недоступна." },
    { title: "Подтвердите", text: "Иконка студии появится на экране приложений." },
  ],
  desktop: [
    { title: "Найдите значок установки", text: "В Chrome или Edge он справа в адресной строке." },
    { title: "Нажмите «Установить»", text: "Студия откроется в отдельном окне со своей иконкой." },
  ],
};

export function InstallGuide() {
  const { tenant } = useStudio();
  const [platform, setPlatform] = useState<Platform>("ios");
  const { state, install } = useInstall();
  const installed = state === "installed";

  useEffect(() => {
    const ua = navigator.userAgent;
    setPlatform(/iphone|ipad|ipod/i.test(ua) ? "ios" : /android/i.test(ua) ? "android" : "desktop");
  }, []);

  return (
    <div className="page" style={{ paddingTop: 28 }}>
      <div className="app-badge" style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 20 }}>
        <span className="brand-logo" style={{ borderRadius: 16, width: 56, height: 56, background: "var(--studio-accent)" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={tenant.pwa.icon192} alt="" />
        </span>
        <div><b style={{ fontSize: 22 }}>{tenant.name}</b><div className="muted">Приложение студии</div></div>
      </div>
      <h1 className="title-xl" style={{ marginTop: 0 }}>Добавьте студию на главный экран</h1>
      <p className="lead">Своя иконка на устройстве. Быстрый доступ к услугам и вашей записи.</p>
      {installed && <p className="lead" style={{ color: "#3ddc84" }}>Приложение уже установлено на этом устройстве.</p>}
      {state === "prompt" && (
        <button type="button" className="pill pill-primary" style={{ marginTop: 22 }} onClick={() => install()}>Установить приложение</button>
      )}
      <h2 className="section-title" style={{ marginTop: 32 }}>Как установить</h2>
      <SegmentedControl label="Платформа" value={platform} onChange={(v) => setPlatform(v as Platform)} layout="fill">
        <SegmentedControlItem value="ios" label="iPhone / iPad" />
        <SegmentedControlItem value="android" label="Android" />
        <SegmentedControlItem value="desktop" label="Компьютер" />
      </SegmentedControl>
      <ol className="install-steps" style={{ marginTop: 18 }}>
        {STEPS[platform].map((s) => <li key={s.title}><div><b>{s.title}</b><span>{s.text}</span></div></li>)}
      </ol>
    </div>
  );
}
