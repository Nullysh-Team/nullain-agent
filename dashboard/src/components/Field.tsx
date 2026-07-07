import type { ReactNode } from "react";

type FieldProps = {
  label: string;
  children: ReactNode;
  hint?: string;
};

export function Field({ label, children, hint }: FieldProps) {
  return (
    <label className="block space-y-2">
      <span className="text-xs tracking-wide text-[#999] uppercase">{label}</span>
      {children}
      {hint ? <span className="block text-xs text-[#666]">{hint}</span> : null}
    </label>
  );
}