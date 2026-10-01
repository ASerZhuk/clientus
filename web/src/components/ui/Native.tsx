"use client";

import { useId } from "react";

interface FieldProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
}

/** Native date/time/number inputs: the best mobile pickers, styled to match. */
export function NativeField({ label, value, onChange, error, ...rest }: FieldProps) {
  const id = useId();
  return (
    <label className="native-field" htmlFor={id}>
      {label}
      <input id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={error ? true : undefined} {...rest} />
      {error && <span className="err" role="alert">{error}</span>}
    </label>
  );
}

export function NativeSelect({ label, value, onChange, options, error }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; error?: string }) {
  const id = useId();
  return (
    <label className="native-field" htmlFor={id}>
      {label}
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {error && <span className="err" role="alert">{error}</span>}
    </label>
  );
}
