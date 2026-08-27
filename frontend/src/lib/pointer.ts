export function hasFinePointer() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(pointer: fine)").matches && window.matchMedia("(hover: hover)").matches;
}

export function isTouchPrimary() {
  return !hasFinePointer();
}
