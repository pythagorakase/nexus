import { NotFound } from "nexus-ui";
// The 404 surface: deliberately quiet and theme-consistent — a mono [ 404 ]
// code over a single NEXUS link home, on the themed background. Rendered in
// the default Veil theme inside a sized, clipped container so the
// min-h-screen centering resolves against a real viewport box.

export const Screen = () => (
  <div
    style={{
      position: "relative",
      width: 900,
      height: 690,
      overflow: "hidden",
    }}
  >
    <NotFound />
  </div>
);
