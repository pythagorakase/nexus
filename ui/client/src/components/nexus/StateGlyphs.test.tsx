import { UI_CONFIG_KEY } from "@/hooks/useUiConfig";
/** Real component/cache/timer/event proof; no module, hook, fetch or action mocks. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { geoEquirectangular } from "d3-geo";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { useSettingsQuery } from "@/hooks/useSettings";
import { LOCAL_MODELS_DOWNLOAD_KEY, LOCAL_MODELS_STATUS_KEY } from "@/hooks/useLocalModels";
import { boundsToFitObject, COINCIDENT_PIN_EPSILON_PX, COINCIDENT_PIN_RING_PX, computeMapBounds, offsetCoincidentPins, PIN_RADIUS_PX } from "@/lib/map-geometry";
import type { LocalModelsStatus } from "@/types/localModels";
import type { Place } from "@shared/schema";
import { KeyStatusGlyph } from "./SettingsPane";
import { LocalModelRows } from "./LocalModelRows";
import { MapPane } from "./MapPane";
import { MapViewProvider } from "./MapViewContext";
import { TopBar } from "./TopBar";
const KNOBS = { poll_busy_ms: 1e8, poll_idle_ms: 1e8, download_poll_ms: 1e8, delete_arm_ms: 250 };
const STATUS: LocalModelsStatus = {
  models_dir: "/models", system_ram_gb: 32,
  catalog: [{ family: "fixture", label: "Fixture Q4", hf_repo: "fixture", subdir: "fixture", filename: "model.gguf", quant: "Q4", size_gb: 32 * 2 ** 30 / 1e9, min_ram_gb: 96 }],
  installed: [{ path: "/models/fixture/model.gguf", filename: "model.gguf", arch: "fixture", quant: "Q4", size_bytes: 32 * 2 ** 30, verified: true, active: false }],
  active: null,
};
const clients: QueryClient[] = [];
function client(status = STATUS) {
  const c = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity } } });
  c.setQueryData([...LOCAL_MODELS_STATUS_KEY], status);
  c.setQueryData(UI_CONFIG_KEY, { announcer: { hold_ms: 5000 } });
  c.setQueryData([...LOCAL_MODELS_DOWNLOAD_KEY], { state: "idle" });
  c.setQueryData(["/api/settings"], { ui: { local_models: KNOBS, theme: "veil" } });
  c.setQueryData(["/api/preferences"], { ui: { theme: "veil" } });
  clients.push(c); return c;
}
function withClient(c: QueryClient, node: React.ReactNode) {
  return <QueryClientProvider client={c}>{node}</QueryClientProvider>;
}
function place(id: number, lng: number, lat: number): Place {
  return { id, name: `Place ${id}`, type: "fixed_location", zone: 1, summary: null, inhabitants: null, history: null, currentStatus: null, extraData: null, createdAt: new Date(), updatedAt: new Date(), coordinates: null, geom: null, geometry: { type: "Point", coordinates: [lng, lat] } };
}
const PLACES = [place(1, 0, 0), place(2, 0, 0), place(3, .02, 0), place(4, 10, 5)];
// jsdom has no layout; deliver only the missing native resize signal.
class CanvasResizeObserver {
  static latest: CanvasResizeObserver;
  constructor(private callback: ResizeObserverCallback) { CanvasResizeObserver.latest = this; }
  observe() {} unobserve() {} disconnect() {}
  deliver() { this.callback([{ contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry], this as unknown as ResizeObserver); }
}
function map() {
  vi.stubGlobal("ResizeObserver", CanvasResizeObserver);
  const c = client();
  c.setQueryData(["/api/places", 4], PLACES);
  c.setQueryData(["/api/zones", 4], [{ id: 1, name: "Fixture", summary: null, boundary: null }]);
  c.setQueryData(["/api/current-place", 4], [{ placeId: 4, name: "Place 4", chunkId: 1 }]);
  for (const p of PLACES) c.setQueryData(["/api/places", p.id, "images", 4], []);
  render(withClient(c, <ThemeProvider><MapViewProvider><MapPane slot={4} /></MapViewProvider></ThemeProvider>));
  const svg = screen.getByTestId("map-svg");
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 600, right: 1000, bottom: 600 }) as DOMRect;
  act(() => CanvasResizeObserver.latest.deliver());
  fireEvent.click(screen.getByTestId("map-zone-1"));
  return svg;
}
function glyph(id: number, sidebar = false) {
  return screen.getByTestId(sidebar ? `map-place-row-${id}` : `map-pin-${id}`).querySelector("[data-map-state]")!;
}
function visibleParts(node: Element) {
  return Array.from(node.querySelectorAll("[data-map-part]")).filter(n => n.getAttribute("display") !== "none");
}
function signature(node: Element) {
  return visibleParts(node).map(n => {
    const d = n.getAttribute("d")!;
    // Remove translation and scale: arcs are circular; straight paths are
    // square when the first edge is horizontal and diamond otherwise.
    const values = d.match(/-?(?:\d*\.)?\d+(?:e[+-]?\d+)?/gi)!.map(Number);
    const kind = d.includes("A") ? "circle" : values[1] === values[3] ? "square" : "diamond";
    return `${kind}:${n.getAttribute("data-map-part")}`;
  }).join(";");
}
function center(node: Element) {
  const d = node.querySelector('[data-map-part="fill"]')!.getAttribute("d")!;
  const v = d.match(/-?(?:\d*\.)?\d+(?:e[+-]?\d+)?/gi)!.map(Number);
  if (d.includes("A")) return { x: (v[0] + v[7]) / 2, y: v[1] };
  return { x: (v[0] + v[4]) / 2, y: (v[1] + v[5]) / 2 };
}
afterEach(() => { cleanup(); clients.splice(0).forEach(c => c.clear()); vi.unstubAllGlobals(); });
describe("glyph-first states", () => {
  it("memory_over_budget_has_a_static_warning_and_normal_does_not", () => {
    for (const ratio of [.5, 1, 1.1]) {
      const c = client({ ...STATUS, catalog: [{ ...STATUS.catalog[0], size_gb: STATUS.catalog[0].size_gb * ratio }], active: { gguf_path: "/models/fixture/model.gguf", ready: true, failed: false } });
      const view = render(withClient(c, <TopBar slot={4} characterName={null} skaldStatus="READY" failedGeneration={null} toastedFailureSessionId={null} frontierClock={null} />));
      const warning = view.container.querySelector(".mem-over-glyph");
      expect(Boolean(warning)).toBe(ratio > 1);
      if (warning) { expect(warning).toHaveAttribute("aria-hidden", "true"); expect(warning).toHaveAttribute("width", "12"); }
      expect(view.container.querySelector(".mem-fill")).toHaveStyle({ width: `${Math.min(ratio * 100, 100).toFixed(1)}%` });
      view.unmount();
    }
    render(withClient(client(), <TopBar slot={4} characterName={null} skaldStatus="READY" failedGeneration={null} toastedFailureSessionId={null} frontierClock={null} />));
    expect(screen.queryByTestId("mem-meter")).not.toBeInTheDocument();
  });
  it("armed_delete_changes_glyph_and_disarming_restores_trash", async () => {
    // SettingsPane passes these settings to LocalModelRows in production.
    // Read the same seeded cache through its real hook, with native timers.
    function ConfiguredRows() {
      const { data: settings } = useSettingsQuery();
      return <ul><LocalModelRows selected={false} onPickLocal={() => {}} knobs={settings?.ui?.local_models} /></ul>;
    }
    render(withClient(client(), <ConfiguredRows />));
    fireEvent.click(screen.getByTestId("lm-toggle-fixture"));
    const button = screen.getByTestId("lm-trash-fixture-Q4");
    // Enabled even in the dimmed exceeds-RAM ready row.
    expect(button).not.toBeDisabled();
    expect(button.querySelector(".lucide-trash2")).toBeInTheDocument();
    expect(button).toHaveAccessibleName("Delete Fixture Q4");
    const armedAt = performance.now();
    fireEvent.click(button);
    expect(screen.getByTestId("lm-trash-fixture-Q4")).toBe(button);
    expect(button.querySelector(".lucide-trash2")).not.toBeInTheDocument();
    expect(button.querySelector(".lucide-triangle-alert")).toHaveAttribute("width", "11");
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(button).toHaveAccessibleName("Confirm delete Fixture Q4");
    await waitFor(() => {
      expect(button).toHaveAttribute("aria-pressed", "true");
      expect(performance.now() - armedAt).toBeGreaterThanOrEqual(KNOBS.delete_arm_ms - 100);
    }, { interval: 5, timeout: KNOBS.delete_arm_ms });
    await waitFor(() => expect(button).toHaveAttribute("aria-pressed", "false"), {
      interval: 5, timeout: KNOBS.delete_arm_ms + 500 - (performance.now() - armedAt),
    });
    expect(performance.now() - armedAt).toBeLessThanOrEqual(KNOBS.delete_arm_ms + 500);
    expect(screen.getByTestId("lm-trash-fixture-Q4")).toBe(button);
    expect(button).toHaveAccessibleName("Delete Fixture Q4");
    expect(button.querySelector(".lucide-trash2")).toBeInTheDocument();
  });
  it("map_states_have_distinct_static_shapes_on_both_surfaces", () => {
    map();
    fireEvent.click(screen.getByTestId("map-place-row-1"));
    fireEvent.pointerEnter(screen.getByTestId("map-pin-3"));
    const signatures = [1, 2, 3, 4].map(id => {
      expect(signature(glyph(id, true))).toBe(signature(glyph(id)));
      const svg = screen.getByTestId(`map-place-row-${id}`).querySelector("svg")!;
      expect(svg).toHaveAttribute("viewBox", "-4.5 -4.5 9 9"); expect(svg).toHaveAttribute("width", "9");
      for (const part of visibleParts(svg)) {
        const d = part.getAttribute("d")!;
        const v = d.match(/-?(?:\d*\.)?\d+(?:e[+-]?\d+)?/gi)!.map(Number);
        const radius = d.includes("A") ? v[2] : Math.max(v[0], v[2], v[4], v[6]);
        const outline = part.getAttribute("data-map-part") === "outline";
        expect(radius).toBe(outline ? 4 : 2.5);
        if (outline) expect(part).toHaveAttribute("stroke-width", "1");
      }
      return signature(glyph(id));
    });
    expect(new Set(signatures).size).toBe(4);
    expect([1, 2, 3, 4].map(id => glyph(id).getAttribute("data-map-state"))).toEqual(["selected", "rest", "hovered", "current"]);
    for (const id of [1, 3]) expect(glyph(id).querySelector('[data-map-part="outline"]')).toHaveClass("animate-pulse");
    for (const id of [1, 4]) {
      fireEvent.pointerEnter(screen.getByTestId(`map-pin-${id}`));
      expect(signature(glyph(id))).toBe(signatures[[1, 2, 3, 4].indexOf(id)]);
      expect(signature(glyph(id, true))).toBe(signature(glyph(id)));
    }
    expect(glyph(4).querySelector('[data-map-part="outline"]')).not.toHaveClass("animate-pulse");
    expect(glyph(2).querySelector('[data-map-part="outline"]')).toHaveAttribute("display", "none");
    fireEvent.click(screen.getByTestId("map-place-row-4"));
    expect(glyph(4)).toHaveAttribute("data-map-state", "current");
    expect(signature(glyph(4, true))).toBe(signature(glyph(4)));
  });
  it("map_layers_keep_identity_through_hover_selection_and_rest", () => {
    map();
    const pin = screen.getByTestId("map-pin-3");
    const fill = pin.querySelector('[data-map-part="fill"]')!;
    const ring = pin.querySelector('[data-map-part="outline"]')!;
    const hit = pin.querySelector("path")!;
    const sameLayers = () => {
      expect(pin.querySelector('[data-map-part="fill"]')).toBe(fill);
      expect(pin.querySelector('[data-map-part="outline"]')).toBe(ring);
      expect(pin.querySelector("path")).toBe(hit);
    };
    expect(glyph(3)).toHaveAttribute("data-map-state", "rest");
    fireEvent.pointerOver(hit);
    expect(glyph(3)).toHaveAttribute("data-map-state", "hovered");
    sameLayers();
    fireEvent.click(screen.getByTestId("map-place-row-3"));
    expect(glyph(3)).toHaveAttribute("data-map-state", "selected");
    sameLayers();
    fireEvent.pointerOut(hit);
    fireEvent.click(screen.getByTestId("map-place-row-1"));
    expect(glyph(3)).toHaveAttribute("data-map-state", "rest");
    sameLayers();
  });
  it("map_state_geometry_keeps_its_screen_size_at_two_zooms", () => {
    const svg = map();
    fireEvent.click(screen.getByTestId("map-place-row-1"));
    const projection = geoEquirectangular().fitSize([1000, 600], boundsToFitObject(computeMapBounds(PLACES)!));
    const coords = new Map(PLACES.map(p => { const [x, y] = projection(p.geometry!.coordinates as [number, number])!; return [p.id, { x, y }]; }));
    const centers: { x: number; y: number }[] = [];
    for (const ticks of [0, 12]) {
      for (let i = 0; i < ticks; i++) fireEvent.wheel(svg, { deltaY: -100, clientX: 500, clientY: 300 });
      const box = svg.getAttribute("viewBox")!.split(" ").map(Number);
      const zoom = 1000 / box[2];
      const displayed = offsetCoincidentPins(coords, COINCIDENT_PIN_EPSILON_PX / zoom, COINCIDENT_PIN_RING_PX / zoom);
      fireEvent.pointerEnter(screen.getByTestId("map-pin-3"));
      for (const id of [1, 2, 3, 4]) {
        const pin = glyph(id), pos = center(pin), expected = displayed.get(id)!;
        expect(pos.x).toBeCloseTo(expected.x, 9); expect(pos.y).toBeCloseTo(expected.y, 9);
        for (const shape of visibleParts(pin)) {
          const radius = shape.getAttribute("data-map-part") === "fill" ? PIN_RADIUS_PX : 8;
          const d = shape.getAttribute("d")!;
          const v = d.match(/-?(?:\d*\.)?\d+(?:e[+-]?\d+)?/gi)!.map(Number);
          const halfSize = d.includes("A") ? v[2] : Math.max(...[v[0], v[2], v[4], v[6]]) - pos.x;
          expect(halfSize * zoom).toBeCloseTo(radius, 9);
          if (radius === 8) expect(Number(shape.getAttribute("stroke-width")) * zoom).toBeCloseTo(1, 9);
        }
        const leader = screen.queryByTestId(`map-pin-leader-${id}`);
        const actual = coords.get(id)!;
        if (Math.hypot(pos.x - actual.x, pos.y - actual.y) > 1e-8) {
          expect(leader).toBeInTheDocument();
          for (const [attr, value] of Object.entries({ x1: actual.x, y1: actual.y, x2: pos.x, y2: pos.y })) expect(Number(leader!.getAttribute(attr))).toBeCloseTo(value, 9);
        } else expect(leader).toBeNull();
      }
      centers.push(center(glyph(3)));
      // Selecting through the real row centers at the true point at each zoom.
      fireEvent.click(screen.getByTestId("map-place-row-1"));
      const centered = svg.getAttribute("viewBox")!.split(" ").map(Number);
      expect(centered[0] + centered[2] / 2).toBeCloseTo(coords.get(1)!.x, 9);
      expect(centered[1] + centered[3] / 2).toBeCloseTo(coords.get(1)!.y, 9);
    }
    expect(centers[0]).not.toEqual(centers[1]); // nearby grouping changes with zoom
  });
  it("required_missing_optional_absent_present_and_verified_have_distinct_glyphs", () => {
    const cases = [{ required: false, present: false, verified: false }, { required: true, present: false, verified: false }, { required: true, present: true, verified: false }, { required: false, present: false, verified: true }];
    const geometry: string[] = [];
    const classes = cases.map(props => {
      const view = render(<KeyStatusGlyph {...props} />), svg = view.container.querySelector("svg")!;
      expect(svg).toHaveAttribute("width", "12");
      geometry.push(Array.from(svg.children).map(n => `${n.tagName}:${Array.from(n.attributes).filter(a => !["fill", "stroke", "class"].includes(a.name)).map(a => `${a.name}=${a.value}`).join(";")}`).join("|"));
      const cls = svg.getAttribute("class")!; view.unmount(); return cls;
    });
    expect(new Set(classes).size).toBe(4);
    expect(new Set(geometry).size).toBe(4);
    expect(classes.map(c => c.split(" ").find(c => c.startsWith("key-glyph-")))).toEqual(["key-glyph-optional-absent", "key-glyph-required-missing", "key-glyph-present", "key-glyph-verified"]);
    for (const present of [false, true]) for (const required of [false, true]) {
      const view = render(<KeyStatusGlyph present={present} required={required} verified />);
      expect(view.container.querySelector(".key-glyph-verified")).toBeInTheDocument(); view.unmount();
    }
  });
});
