"use client";

import { IconButton } from "@/components/ui/Pill";
import { ArrowUp } from "@phosphor-icons/react";
import { BottomSheet } from "@astryxdesign/core/BottomSheet";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { navigateFromSheet, useBackClose } from "@/lib/hooks";
import { useRouter } from "next/navigation";
import { useStudio } from "@/components/StudioProviders";
import { useBooking } from "./BookingProvider";
import type { AssistantOption, AssistantReply } from "@/lib/types";

type BookAction = Extract<NonNullable<AssistantReply["action"]>, { type: "book" }>;

interface Msg {
  role: "me" | "bot";
  text: string;
  options?: AssistantOption[];
  action?: AssistantReply["action"];
}

interface Props {
  slug: string;
  audience: "client" | "owner";
  isOpen: boolean;
  onClose: () => void;
  autoAsk?: string;
}

/** Deterministic assistant: chips and free text go to the server, answers come from the database. */
export function AssistantSheet({ slug, audience, isOpen, onClose, autoAsk }: Props) {
  const base = audience === "owner" ? `/api/s/${slug}/owner/assistant` : `/api/s/${slug}/assistant`;
  const booking = useBooking();
  const router = useRouter();
  const qc = useQueryClient();
  const { href } = useStudio();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useBackClose(isOpen, onClose);

  const examples = useQuery({ queryKey: ["assistant-examples", slug, audience], queryFn: () => api<{ examples: string[] }>(`${base}/examples`), enabled: isOpen, staleTime: Infinity });

  const ask = useMutation({
    mutationFn: (v: { text: string; context?: AssistantOption["context"]; history: { role: Msg["role"]; text: string }[] }) =>
      api<AssistantReply>(base, { method: "POST", body: { text: v.text, history: v.history, ...(v.context && Object.keys(v.context).length ? { context: v.context } : {}) } }),
    onSuccess: (r) => {
      setMessages((m) => [...m, { role: "bot", text: r.text, options: r.options, action: r.action }]);
      if (audience !== "owner") return;
      if (r.action?.type === "open") navigateFromSheet(router.push, href(r.action.to)); // no model: open the form at once
      if (r.action?.type === "done") qc.invalidateQueries(); // the assistant changed data: refresh every cabinet screen
    },
    onError: (e) => setMessages((m) => [...m, { role: "bot", text: e instanceof ApiError ? e.message : "Не удалось получить ответ." }]),
  });

  const send = (value: string, context?: AssistantOption["context"]) => {
    const t = value.trim();
    if (!t || ask.isPending) return;
    setMessages((m) => [...m, { role: "me", text: t }]);
    setText("");
    ask.mutate({ text: t, context, history: messages.slice(-6).map((m) => ({ role: m.role, text: m.text.slice(0, 1500) })) });
  };

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages, ask.isPending]); // newer browsers return a Promise here; an effect must not return it
  const asked = useRef(false);
  useEffect(() => {
    if (!isOpen) asked.current = false;
    else if (autoAsk && !asked.current) { asked.current = true; send(autoAsk); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, autoAsk]);

  const book = (a: BookAction) => {
    // close the chat first (it pops its history entry), then open the booking form with the choice already made
    const go = () => booking.open({ serviceId: a.service_id, start: a.start_min });
    if ((history.state as { sheet?: boolean } | null)?.sheet) window.addEventListener("popstate", () => setTimeout(go, 0), { once: true });
    else setTimeout(go, 0);
    onClose();
  };

  return (
    <BottomSheet isOpen={isOpen} onOpenChange={(o) => !o && onClose()} label={audience === "owner" ? "Помощник владельца" : "Помощник"} height="tall">
      <div className="chat-shell">
        <div className="chat" aria-live="polite">
          <div className="bubble bot">
            {audience === "owner" ? "Спросите про записи или скажите, что сделать. Например: «добавь услугу замена масла 1500 ₽ 20 минут», «в субботу выходной», «запиши Ивана на завтра в 10»." : "Помогу записаться. Напишите, что нужно сделать и когда удобно, — подберу свободное время."}
          </div>
          {messages.length === 0 && (
            <div className="chips chat-chips">
              {(examples.data?.examples ?? []).map((e) => (
                <button key={e} className="chip-btn" type="button" onClick={() => send(e)}>
                  {e}
                </button>
              ))}
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className="stack" style={{ gap: 8, alignItems: m.role === "me" ? "flex-end" : "flex-start" }}>
              <div className={`bubble ${m.role}`}>{m.text}</div>
              {m.options && i === messages.length - 1 && (
                <div className="chips chat-chips">
                  {m.options.map((o) => (
                    <button key={o.label} className={`chip-btn ${o.action ? "chip-time" : ""}`} type="button" onClick={() => (o.action && audience === "client" ? book(o.action) : send(o.text, o.context))}>
                      {o.label}
                    </button>
                  ))}
                </div>
              )}
              {m.action?.type === "done" && i === messages.length - 1 && (
                <button className="chip-btn chat-link" type="button" onClick={() => navigateFromSheet(router.push, href((m.action as { to: string }).to))}>
                  Посмотреть
                </button>
              )}
              {m.action?.type === "book" && audience === "client" && i === messages.length - 1 && (
                <button className="pill pill-primary pill-sm" type="button" onClick={() => book(m.action as BookAction)}>
                  Записаться
                </button>
              )}
            </div>
          ))}
          {ask.isPending && <div className="bubble bot typing" aria-label="Печатает"><i /><i /><i /></div>}
          <div ref={endRef} />
        </div>
        <form
          className="chat-composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
        >
          <input aria-label="Сообщение" value={text} onChange={(e) => setText(e.target.value)} placeholder={audience === "owner" ? "Например: добавь услугу" : "Например: развал в субботу утром"} enterKeyHint="send" />
          <IconButton label="Отправить" icon={<ArrowUp weight="bold" />} variant="primary" onClick={() => send(text)} isDisabled={!text.trim() || ask.isPending} />
        </form>
      </div>
    </BottomSheet>
  );
}
