import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useStudio } from "./StudioContext";
import { studioSteps } from "./StudioRail";
import { openIssueReporter, openKitDialog } from "./studioEvents";
import { useTheme } from "./theme";

type Command = { group: string; label: string; hint: string; run: () => void };

// Navigation and existing non-hardware actions only. Every hardware change keeps its own preview.
export function CommandPalette() {
  const studio = useStudio();
  const navigate = useNavigate();
  const [theme, setTheme] = useTheme();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const open = !!studio?.paletteOpen;
  // Modal behaviour: focus moves in on open and returns to where it was on close.
  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    setQuery(""); setCursor(0);
    requestAnimationFrame(() => input.current?.focus());
    return () => { const back = returnFocus.current; if (back && document.contains(back)) requestAnimationFrame(() => back.focus()); };
  }, [open]);
  const commands = useMemo<Command[]>(() => {
    if (!studio) return [];
    const go = (path: string) => () => navigate(path);
    const list: Command[] = [
      { group: "Go to", label: "My Rack", hint: "screen", run: go("/simple") },
      ...studioSteps.map((step, index) => ({ group: "Go to", label: `${index + 1} · ${step.name}`, hint: "screen", run: go(step.path) })),
      { group: "Go to", label: "Run history", hint: "screen", run: go("/setup/history") },
    ];
    for (const item of studio.devices) {
      const device = encodeURIComponent(item.deviceId || item.id);
      if (item.kind === "server" && item.deviceId) list.push({ group: item.name, label: `Connection, drives and RAID · ${item.name}`, hint: "screen", run: go(`/setup/connect?device=${device}`) });
    }
    list.push(
      { group: studio.profileName || "Kit", label: "Rename kit", hint: "", run: () => openKitDialog("rename") },
      { group: studio.profileName || "Kit", label: "Save as new kit", hint: "", run: () => openKitDialog("copy") },
      { group: studio.profileName || "Kit", label: "Build reports", hint: "", run: () => openKitDialog("reports") },
      { group: "Settings", label: theme === "dark" ? "Use the light theme" : "Use the dark theme", hint: "appearance", run: () => setTheme(theme === "dark" ? "light" : "dark") },
      { group: "Settings", label: "Report an issue", hint: "", run: openIssueReporter },
    );
    return list;
  }, [studio, navigate, theme, setTheme]);
  if (!studio || !open) return null;
  const needle = query.trim().toLowerCase();
  const shown = needle ? commands.filter(command => `${command.group} ${command.label}`.toLowerCase().includes(needle)) : commands;
  const safeCursor = Math.min(cursor, Math.max(0, shown.length - 1));
  function run(command: Command | undefined) {
    if (!command || !studio) return;
    studio.setPaletteOpen(false);
    command.run();
  }
  let lastGroup = "";
  function trap(event: React.KeyboardEvent) {
    if (!studio) return;
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); studio.setPaletteOpen(false); return; }
    if (event.key !== "Tab" || !panel.current) return;
    const items = Array.from(panel.current.querySelectorAll<HTMLElement>("input,button:not([disabled])"));
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  return <div className="sd-scrim" onKeyDown={trap} onMouseDown={event => { if (event.target === event.currentTarget) studio.setPaletteOpen(false); }}>
    <div ref={panel} className="sd-palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="sd-pal-h">
        <svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M10.4 10.4L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
        <input ref={input} value={query} aria-label="Command" placeholder="Type a command or a device name"
          onChange={event => { setQuery(event.target.value); setCursor(0); }}
          onKeyDown={event => {
            if (event.key === "ArrowDown") { event.preventDefault(); setCursor(Math.min(shown.length - 1, safeCursor + 1)); }
            else if (event.key === "ArrowUp") { event.preventDefault(); setCursor(Math.max(0, safeCursor - 1)); }
            else if (event.key === "Enter") { event.preventDefault(); run(shown[safeCursor]); }
          }} />
        <kbd>Esc</kbd>
      </div>
      <ul role="listbox" aria-label="Commands">
        {shown.length === 0 && <li className="g">No matching command</li>}
        {shown.map((command, index) => {
          const header = command.group !== lastGroup ? <li className="g" key={`g-${command.group}-${index}`} role="presentation">{command.group}</li> : null;
          lastGroup = command.group;
          return [header, <li key={`${command.group}-${command.label}`} role="presentation"><button type="button" role="option" aria-selected={index === safeCursor} className={index === safeCursor ? "active" : undefined} onMouseEnter={() => setCursor(index)} onClick={() => run(command)}><span>{command.label}</span><small>{command.hint}</small></button></li>];
        })}
      </ul>
      <div className="sd-pal-f"><span><kbd>↑</kbd><kbd>↓</kbd>choose</span><span><kbd>↵</kbd>run</span><span><kbd>Esc</kbd>close</span><span>Nothing here writes to hardware.</span></div>
    </div>
  </div>;
}
