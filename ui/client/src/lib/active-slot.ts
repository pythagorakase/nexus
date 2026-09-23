/** The last successfully opened story or wizard in this browser. */
export function getActiveSlot(): number | null {
  try {
    const value = localStorage.getItem("activeSlot");
    return value && /^[1-5]$/.test(value) ? Number(value) : null;
  } catch {
    return null;
  }
}

export function rememberActiveSlot(slot: number): void {
  try {
    localStorage.setItem("activeSlot", String(slot));
  } catch {
    // Storage may be disabled; the current session can still be used.
  }
}
