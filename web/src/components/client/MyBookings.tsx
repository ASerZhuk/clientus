"use client";

import { Button } from "@/components/ui/Pill";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Banner } from "@astryxdesign/core/Banner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useStudio } from "@/components/StudioProviders";
import { api, ApiError, studioApi } from "@/lib/api";
import { adoptTokenFromHash, readBookings, removeBooking, saveBooking, type StoredBooking } from "@/lib/booking-store";
import type { ClientBooking } from "@/lib/types";
import { BookingDetails } from "./BookingDetails";
import { useBooking } from "./BookingProvider";

function MyBooking({ stored }: { stored: StoredBooking }) {
  const { slug } = useStudio();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["my", slug, stored.id],
    queryFn: () => api<ClientBooking>(`${studioApi(slug)}/my/booking`, { bookingToken: stored.token }),
    retry: false,
  });
  if (q.isPending) return <Skeleton height={220} radius={4} />;
  if (q.isError) {
    const gone = q.error instanceof ApiError && (q.error.status === 404 || q.error.status === 401);
    return (
      <Banner status="error" title={gone ? "Запись не найдена" : "Не удалось загрузить запись"} description={(q.error as ApiError).message}
        endContent={gone ? <Button size="sm" label="Убрать" onClick={() => { removeBooking(slug, stored.id); qc.invalidateQueries({ queryKey: ["stored", slug] }); location.reload(); }} /> : <Button size="sm" label="Повторить" onClick={() => q.refetch()} />} />
    );
  }
  return <BookingDetails booking={q.data} token={stored.token} onChanged={(b) => qc.setQueryData(["my", slug, stored.id], b)} />;
}

export function MyBookings() {
  const { slug } = useStudio();
  const booking = useBooking();
  const [items, setItems] = useState<StoredBooking[] | null>(null);
  useEffect(() => {
    const t = adoptTokenFromHash(slug);
    if (t) {
      // a link shared by the studio: resolve it to a booking and remember it on this device
      api<ClientBooking>(`${studioApi(slug)}/my/booking`, { bookingToken: t })
        .then((b) => { saveBooking(slug, { id: b.id, token: t, service_name: b.service_name, start_min: b.start_min }); setItems(readBookings(slug)); })
        .catch(() => setItems(readBookings(slug)));
    } else setItems(readBookings(slug));
  }, [slug]);

  if (items === null) return <div className="page stack" style={{ paddingTop: 28 }}><Skeleton height={220} radius={4} /></div>;
  if (items.length === 0)
    return (
      <div className="page" style={{ paddingTop: 28 }}>
        <h1 className="title-xl" style={{ marginTop: 0 }}>Здесь будет ваша запись</h1>
        <p className="lead">Выберите услугу и время. Запись хранится только в этом браузере — без регистрации. Для восстановления откройте сохранённую приватную ссылку.</p>
        <button type="button" className="pill pill-primary" style={{ marginTop: 24 }} onClick={() => booking.open()}>Выбрать услугу</button>
      </div>
    );
  return (
    <div className="page stack" style={{ gap: 24, paddingTop: 28 }}>
      <h1 className="title-xl" style={{ margin: 0 }}>Моя запись</h1>
      {items.map((s) => <MyBooking key={s.id} stored={s} />)}
    </div>
  );
}
