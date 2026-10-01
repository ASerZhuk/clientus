import type { Metadata } from "next";

export const metadata: Metadata = { title: "Нет соединения", robots: { index: false } };

export default function OfflinePage() {
  return (
    <main className="page" style={{ paddingBlock: "18vh", textAlign: "center" }}>
      <h1 style={{ fontSize: 24 }}>Нет соединения</h1>
      <p className="muted">Запись и свободное время нужны интернет. Проверьте связь и обновите страницу — последние загруженные данные студии остаются доступны.</p>
    </main>
  );
}
