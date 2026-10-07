import { useEffect, useState } from "react";

// Light is the default. Dark is only ever an explicit operator choice, never the OS setting.
export type StudioTheme = "light" | "dark";
const THEME_KEY = "lab-builder-theme";
const THEME_EVENT = "lab-builder-theme-change";

export function readTheme(): StudioTheme {
  try {
    return window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: StudioTheme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
}

export function setTheme(theme: StudioTheme) {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage can be blocked; the choice then lasts for this page only.
  }
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}

export function useTheme(): [StudioTheme, (theme: StudioTheme) => void] {
  const [theme, setLocal] = useState<StudioTheme>(() => (typeof window === "undefined" ? "light" : readTheme()));
  useEffect(() => {
    const sync = (event: Event) => setLocal((event as CustomEvent<StudioTheme>).detail === "dark" ? "dark" : "light");
    window.addEventListener(THEME_EVENT, sync);
    return () => window.removeEventListener(THEME_EVENT, sync);
  }, []);
  return [theme, setTheme];
}
