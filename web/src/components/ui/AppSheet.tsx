"use client";

import { BottomSheet } from "@astryxdesign/core/BottomSheet";
import { X } from "@phosphor-icons/react";
import { IconButton } from "@/components/ui/Pill";
import { useBackClose } from "@/lib/hooks";

/** Every sheet in the app: same container, Back button closes it, forms use the tall variant (keyboard-safe). */
export function AppSheet({ isOpen, onClose, label, title, height = "tall", bare = false, children }: { bare?: boolean; isOpen: boolean; onClose: () => void; label: string; title?: string; height?: "hug" | "capped" | "tall"; children: React.ReactNode }) {
  useBackClose(isOpen, onClose);
  return (
    <BottomSheet isOpen={isOpen} onOpenChange={(o) => !o && onClose()} label={label} height={height} purpose="form">
      <div className="page sheet-body stack">
        {title && !bare && (
          <div className="sheet-head">
            <h2 className="sheet-title">{title}</h2>
            <IconButton label="Закрыть" icon={<X size={26} />} variant="ghost" onClick={onClose} />
          </div>
        )}
        {children}
      </div>
    </BottomSheet>
  );
}
