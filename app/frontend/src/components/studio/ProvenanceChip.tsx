import type { ReactNode } from "react";

// One chip for every provenance the lab build rules name (section 3).
// Only "proven" may render green, and it must always carry its time.
export type Provenance = "proven" | "saved" | "recorded" | "suggested" | "blank" | "warn" | "danger";

const defaults: Record<Provenance, string> = {
  proven: "proven",
  saved: "saved plan",
  recorded: "recorded",
  suggested: "suggested",
  blank: "not known yet",
  warn: "needs a look",
  danger: "failed",
};

export function shortTime(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (date.toDateString() === now.toDateString()) return time;
  return `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")} ${time}`;
}

export function ProvenanceChip({ kind, time, children, size = "xs", title }: {
  kind: Provenance; time?: string | null; children?: ReactNode; size?: "xs" | "md" | "long"; title?: string;
}) {
  // A "proven" chip without a timestamp is not proof: show it as blank instead.
  const effective: Provenance = kind === "proven" && !shortTime(time) ? "blank" : kind;
  const stamp = shortTime(time);
  const label = children ?? (effective === "blank" && kind === "proven" ? "no proof" : defaults[effective]);
  return <span className={`sd-chip sd-chip-${effective} ${size === "md" ? "" : size === "long" ? "sd-chip-long" : "sd-chip-xs"}`} data-provenance={effective} title={title}>
    {effective === "saved" && <svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13l.7-2.8 7.2-7.2a1.4 1.4 0 012 2l-7.2 7.2z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>}
    {effective === "recorded" && <svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M5.2 8.2l1.9 1.9 3.7-4.2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>}
    <span>{label}{stamp && (effective === "proven" || effective === "recorded") ? ` · ${stamp}` : ""}</span>
  </span>;
}
