import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine. Exercise actual sizing in the browser; this
// supplies the observer lifecycle for component interaction tests.
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};


// jsdom has no media-query engine. Narrow-layout tests supply change events.
if (window.matchMedia === undefined) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (media: string) => ({
      matches: false,
      media,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    }),
  });
}
