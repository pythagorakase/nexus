/**
 * Fading-scrollbars module tests: the scroll listener marks the scrolled
 * element active and clears the mark after the idle delay. (The visual
 * fade itself is CSS - covered by the real-browser verification pass.)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  installFadingScrollbars,
  readScrollbarIdleMs,
  SCROLLBAR_ACTIVE_CLASS,
} from "./fading-scrollbars";

const IDLE_MS = 40;

describe("readScrollbarIdleMs", () => {
  afterEach(() => {
    document.documentElement.style.removeProperty("--scrollbar-idle-ms");
  });

  it("reads the pinned idle delay", () => {
    document.documentElement.style.setProperty("--scrollbar-idle-ms", "1000");
    expect(readScrollbarIdleMs(document)).toBe(1000);
  });

  it("fails loud when the tunable is missing", () => {
    expect(() => readScrollbarIdleMs(document)).toThrow(/--scrollbar-idle-ms/);
  });
});

describe("installFadingScrollbars", () => {
  let uninstall: () => void;
  let pane: HTMLDivElement;

  beforeEach(() => {
    vi.useFakeTimers();
    document.documentElement.style.setProperty(
      "--scrollbar-idle-ms",
      String(IDLE_MS),
    );
    pane = document.createElement("div");
    document.body.appendChild(pane);
    uninstall = installFadingScrollbars(document);
  });

  afterEach(() => {
    uninstall();
    pane.remove();
    document.documentElement.style.removeProperty("--scrollbar-idle-ms");
    document.documentElement.classList.remove(SCROLLBAR_ACTIVE_CLASS);
    vi.useRealTimers();
  });

  it("marks a scrolled element active, then clears it after the idle delay", () => {
    pane.dispatchEvent(new Event("scroll"));
    expect(pane.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(true);

    vi.advanceTimersByTime(IDLE_MS - 1);
    expect(pane.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(true);

    vi.advanceTimersByTime(1);
    expect(pane.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(false);
  });

  it("keeps the mark alive while scrolling continues", () => {
    pane.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(IDLE_MS - 5);
    pane.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(IDLE_MS - 5);
    expect(pane.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(true);
    vi.advanceTimersByTime(5);
    expect(pane.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(false);
  });

  it("tracks independent scrollers independently", () => {
    const other = document.createElement("div");
    document.body.appendChild(other);

    pane.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(IDLE_MS / 2);
    other.dispatchEvent(new Event("scroll"));

    vi.advanceTimersByTime(IDLE_MS / 2);
    expect(pane.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(false);
    expect(other.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(true);

    other.remove();
  });

  it("routes document-level scrolls to the root element", () => {
    document.dispatchEvent(new Event("scroll"));
    expect(
      document.documentElement.classList.contains(SCROLLBAR_ACTIVE_CLASS),
    ).toBe(true);
    vi.advanceTimersByTime(IDLE_MS);
    expect(
      document.documentElement.classList.contains(SCROLLBAR_ACTIVE_CLASS),
    ).toBe(false);
  });

  it("stops listening after uninstall", () => {
    uninstall();
    pane.dispatchEvent(new Event("scroll"));
    expect(pane.classList.contains(SCROLLBAR_ACTIVE_CLASS)).toBe(false);
    // Re-install so afterEach uninstall stays valid.
    uninstall = installFadingScrollbars(document);
  });
});
