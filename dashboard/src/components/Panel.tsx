import type { ReactNode } from "react";

type PanelProps = {
  title: string;
  children: ReactNode;
  action?: ReactNode;
};

export function Panel({ title, children, action }: PanelProps) {
  return (
    <section className="border border-[#333] bg-black/60 p-6 shadow-[0_0_30px_rgba(255,255,255,0.04)]">
      <div className="mb-5 flex items-center justify-between gap-4 border-b border-[#222] pb-4">
        <h2 className="text-sm tracking-[0.2em] text-[#999] uppercase">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}