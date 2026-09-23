import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine. Exercise actual sizing in the browser; this
// supplies the observer lifecycle for component interaction tests.
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
