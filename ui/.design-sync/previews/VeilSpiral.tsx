import { VeilSpiral } from "nexus-ui";
// The living logarithmic-spiral hero behind the Veil splash — draws its own
// NEXUS wordmark (Megrim) onto a canvas; fills its parent.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "veil");

export const Hero = () => (
  <div style={{ position: "relative", width: 620, height: 400 }}>
    <VeilSpiral />
  </div>
);
