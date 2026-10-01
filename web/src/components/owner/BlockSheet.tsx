"use client";

import { Button } from "@/components/ui/Pill";
import { Banner } from "@astryxdesign/core/Banner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useStudio, useVocab } from "@/components/StudioProviders";
import { AppSheet } from "@/components/ui/AppSheet";
import { Input } from "@/components/ui/Input";
import { NativeField, NativeSelect } from "@/components/ui/Native";
import { api, ApiError, ownerApi } from "@/lib/api";
import { localToMinute, timeOf } from "@/lib/format";
import type { OwnerBlock } from "@/lib/types";
import { refreshSchedule } from "./invalidate";

export function BlockSheet({ isOpen, onClose, defaultDate, resources, blocks }: { isOpen: boolean; onClose: () => void; defaultDate: string; resources: { id: number; name: string }[]; blocks: OwnerBlock[] }) {
  const { slug, tenant } = useStudio();
  const vocab = useVocab();
  const qc = useQueryClient();
  const tz = tenant.timezone;
  const [f, setF] = useState({ resource: "", from: defaultDate, fromTime: "09:00", to: defaultDate, toTime: "18:00", note: "" });
  const [error, setError] = useState("");
  useEffect(() => { if (isOpen) { setF((p) => ({ ...p, from: defaultDate, to: defaultDate, resource: p.resource || String(resources[0]?.id ?? "") })); setError(""); } }, [isOpen, defaultDate, resources]);
  const add = useMutation({
    mutationFn: () => api(`${ownerApi(slug)}/blocks`, { method: "POST", body: { resource_id: Number(f.resource), start_min: localToMinute(f.from, f.fromTime, tz), end_min: localToMinute(f.to, f.toTime, tz), note: f.note } }),
    onSuccess: () => { refreshSchedule(qc, slug); onClose(); },
    onError: (e) => setError(e instanceof ApiError ? (e.code === "slot_unavailable" ? "В это время здесь уже есть запись или блокировка." : e.message) : "Не удалось."),
  });
  const remove = useMutation({ mutationFn: (id: number) => api(`${ownerApi(slug)}/blocks/${id}`, { method: "DELETE" }), onSuccess: () => refreshSchedule(qc, slug) });
  return (
    <AppSheet isOpen={isOpen} onClose={onClose} label={vocab("resource_block")} title={vocab("resource_block")}>
      <p className="muted" style={{ margin: 0 }}>Время станет недоступно для записи (ремонт, обслуживание, личное дело).</p>
      <NativeSelect label={vocab("resource_one").replace(/^./, (c) => c.toUpperCase())} value={f.resource} onChange={(v) => setF({ ...f, resource: v })} options={resources.map((r) => ({ value: String(r.id), label: r.name }))} />
      <div className="two"><NativeField label="С даты" type="date" value={f.from} onChange={(v) => setF({ ...f, from: v })} /><NativeField label="Время" type="time" step={900} value={f.fromTime} onChange={(v) => setF({ ...f, fromTime: v })} /></div>
      <div className="two"><NativeField label="По дату" type="date" value={f.to} onChange={(v) => setF({ ...f, to: v })} /><NativeField label="Время" type="time" step={900} value={f.toTime} onChange={(v) => setF({ ...f, toTime: v })} /></div>
      <Input label="Причина" isOptional value={f.note} onChange={(v) => setF({ ...f, note: v })} />
      {error && <Banner status="error" title={error} />}
      <Button label="Заблокировать" variant="primary" size="lg" isLoading={add.isPending} isDisabled={!f.resource} onClick={() => { setError(""); add.mutate(); }} />
      {blocks.length > 0 && (
        <div className="stack">
          <b>Активные блокировки в этом периоде</b>
          {blocks.map((b) => (
            <div key={b.id} className="row-between panel">
              <span>{resources.find((r) => r.id === b.resource_id)?.name}: {timeOf(b.start_min, tz)}–{timeOf(b.end_min, tz)}{b.note ? ` · ${b.note}` : ""}</span>
              <Button label="Снять" size="sm" variant="ghost" isLoading={remove.isPending} onClick={() => remove.mutate(b.id)} />
            </div>
          ))}
        </div>
      )}
    </AppSheet>
  );
}
