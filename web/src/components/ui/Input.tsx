"use client";

import { TextInput } from "@astryxdesign/core/TextInput";

interface Props {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  type?: "text" | "password" | "email";
  placeholder?: string;
  inputMode?: "text" | "tel" | "email" | "numeric" | "decimal";
  autoComplete?: string;
  isOptional?: boolean;
  description?: string;
  name?: string;
  onEnter?: () => void;
  isDisabled?: boolean;
}

/** Astryx TextInput with the mobile keyboard hints every form here needs. */
export function Input({ error, inputMode, name, isOptional, ...rest }: Props) {
  return (
    <TextInput
      {...rest}
      htmlName={name}
      isOptional={isOptional}
      status={error ? { type: "error", message: error } : undefined}
      // @ts-expect-error inputMode is forwarded to the native <input> through rest props
      inputMode={inputMode}
    />
  );
}
