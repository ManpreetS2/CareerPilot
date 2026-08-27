import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const THEME_KEY = "careerpilot-theme";
const MOTION_KEY = "careerpilot-reduced-motion";

const ThemeContext = createContext<{
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (next: ThemePreference) => void;
  reducedMotion: boolean;
  appReducedMotion: boolean;
  setReducedMotion: (next: boolean) => void;
} | null>(null);

function readPreference(): ThemePreference {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  if (stored === "dark" || stored === "light") return stored;
  return "system";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const [osReduced, setOsReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [appReduced, setAppReduced] = useState(() => localStorage.getItem(MOTION_KEY) === "1");

  useEffect(() => {
    const color = window.matchMedia("(prefers-color-scheme: dark)");
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onColor = () => setSystemDark(color.matches);
    const onMotion = () => setOsReduced(motion.matches);
    color.addEventListener("change", onColor);
    motion.addEventListener("change", onMotion);
    return () => {
      color.removeEventListener("change", onColor);
      motion.removeEventListener("change", onMotion);
    };
  }, []);

  const resolved: ResolvedTheme =
    preference === "system" ? (systemDark ? "dark" : "light") : preference;
  const reducedMotion = appReduced || osReduced;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
    document.documentElement.dataset.theme = resolved;
    document.documentElement.classList.toggle("reduce-motion", reducedMotion);
    localStorage.setItem(THEME_KEY, preference);
    localStorage.setItem(MOTION_KEY, appReduced ? "1" : "0");
  }, [preference, resolved, reducedMotion, appReduced]);

  const value = useMemo(
    () => ({
      preference,
      resolved,
      setPreference: setPreferenceState,
      reducedMotion,
      appReducedMotion: appReduced,
      setReducedMotion: setAppReduced,
    }),
    [preference, resolved, reducedMotion, appReduced],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme requires ThemeProvider");
  return ctx;
}
