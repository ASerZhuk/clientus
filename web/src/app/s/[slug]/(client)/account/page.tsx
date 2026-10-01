import type { Metadata } from "next";
import Link from "next/link";
import { getBase } from "@/lib/server";

export const metadata: Metadata = { title: "Профиль", robots: { index: false } };

export default async function AccountPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const base = await getBase(slug);
  return (
    <div className="page" style={{ paddingTop: 28 }}>
      <h1 className="title-xl" style={{ marginTop: 0 }}>Профиль клиента</h1>
      <p className="lead">Регистрация не нужна. Записи хранятся в этом браузере, а ссылку на запись студия может прислать вам отдельно.</p>
      <div className="stack" style={{ marginTop: 28, gap: 14 }}>
        <Link href={`${base}/my`} className="pill pill-primary">Открыть мои записи</Link>
        <div className="contact-card">
          <b style={{ fontSize: 20 }}>Вы владелец студии?</b>
          <span className="muted">Войдите в кабинет, чтобы управлять записями, ценами и расписанием.</span>
          <Link href={`${base}/owner`} className="pill pill-outline">Открыть кабинет студии</Link>
        </div>
      </div>
    </div>
  );
}
