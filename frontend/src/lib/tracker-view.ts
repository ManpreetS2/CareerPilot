export type TrackerView = "kanban" | "list";

function scopedKey(userId: number) {
  return `careerpilot.tracker-view.u${userId}`;
}

export function defaultTrackerView(): TrackerView {
  if (typeof window === "undefined") return "list";
  return window.matchMedia("(min-width: 1024px)").matches ? "kanban" : "list";
}

export function readTrackerView(userId: number): TrackerView {
  try {
    const raw = localStorage.getItem(scopedKey(userId));
    if (raw === "kanban" || raw === "list") return raw;
  } catch {
    /* ignore */
  }
  return defaultTrackerView();
}

export function saveTrackerView(userId: number, view: TrackerView) {
  localStorage.setItem(scopedKey(userId), view);
}
