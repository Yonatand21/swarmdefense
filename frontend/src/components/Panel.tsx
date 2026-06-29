import type { ReactNode } from "react";

export function Panel({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h3>{title}</h3>
        {hint && <span className="panel-hint">{hint}</span>}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}
