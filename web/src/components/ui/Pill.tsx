"use client";

import Link from "next/link";
import { Children, isValidElement } from "react";

/**
 * The app's own buttons and segmented control. The props mirror the few Astryx ones we used
 * (label, variant, size, icon, isLoading, isDisabled, width, href), so screens read the same
 * but every action looks like the studio design: big rounded pills.
 */
type Variant = "primary" | "secondary" | "ghost" | "destructive";

interface ButtonProps {
  label: string;
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  icon?: React.ReactNode;
  endContent?: React.ReactNode;
  isLoading?: boolean;
  isDisabled?: boolean;
  width?: string | number;
  href?: string;
  target?: string;
  rel?: string;
  type?: "button" | "submit";
  onClick?: (e: React.MouseEvent) => void;
  as?: unknown; // accepted for source compatibility with Astryx; links are always routed here
  elevation?: string;
  tooltip?: string;
}

const CLASS: Record<Variant, string> = { primary: "pill-primary", secondary: "pill-outline", ghost: "pill-ghost", destructive: "pill-danger" };

export function Button({ label, variant = "secondary", size = "md", icon, endContent, isLoading, isDisabled, width, href, target, rel, type = "button", onClick, tooltip }: ButtonProps) {
  const cls = `pill ${CLASS[variant]} pill-${size}`;
  const style = width ? { width: typeof width === "number" ? `${width}px` : width } : undefined;
  const content = (
    <>
      {isLoading ? <span className="spin" aria-hidden /> : icon}
      <span>{label}</span>
      {endContent}
    </>
  );
  if (href) {
    const external = /^(https?:|tel:|mailto:)/.test(href);
    return external ? (
      <a className={cls} style={style} href={href} target={target} rel={rel} title={tooltip} onClick={onClick}>{content}</a>
    ) : (
      <Link className={cls} style={style} href={href} onClick={onClick}>{content}</Link>
    );
  }
  return (
    <button className={cls} style={style} type={type} disabled={isDisabled || isLoading} aria-busy={isLoading || undefined} title={tooltip} onClick={onClick}>
      {content}
    </button>
  );
}

interface IconButtonProps {
  label: string;
  icon: React.ReactNode;
  variant?: Variant;
  size?: "sm" | "md" | "lg";
  elevation?: string;
  isLoading?: boolean;
  isDisabled?: boolean;
  onClick?: (e: React.MouseEvent) => void;
}

export function IconButton({ label, icon, variant = "secondary", size = "md", isLoading, isDisabled, onClick }: IconButtonProps) {
  return (
    <button type="button" className={`round round-${size} ${variant === "primary" ? "round-primary" : variant === "ghost" ? "round-ghost" : ""}`} aria-label={label} title={label} disabled={isDisabled || isLoading} onClick={onClick}>
      {isLoading ? <span className="spin" aria-hidden /> : icon}
    </button>
  );
}

interface ItemProps {
  value: string;
  label: string;
}
/** Declarative marker: read by SegmentedControl, renders nothing itself. */
export function SegmentedControlItem(_props: ItemProps): null {
  return null;
}

export function SegmentedControl({ value, onChange, label, children }: { value: string; onChange: (v: string) => void; label: string; layout?: string; children: React.ReactNode }) {
  const items = Children.toArray(children).filter(isValidElement).map((c) => (c as React.ReactElement<ItemProps>).props);
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {items.map((it) => (
        <button key={it.value} type="button" role="radio" aria-checked={value === it.value} className="seg-item" onClick={() => onChange(it.value)}>
          {it.label}
        </button>
      ))}
    </div>
  );
}
