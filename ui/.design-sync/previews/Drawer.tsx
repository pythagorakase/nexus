import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerFooter,
  DrawerTitle,
  DrawerDescription,
  Button,
} from "nexus-ui";

// Bottom drawer (vaul default) — a save-slot detail sheet sliding up from the
// foot of the screen, with the grab handle the component renders for top/bottom.
export const SlotDetails = () => (
  <Drawer open modal={false}>
    <DrawerContent>
      <DrawerHeader>
        <DrawerTitle>Save Slot 02 — The Veil</DrawerTitle>
        <DrawerDescription>
          Chapter Seven · 18,420 words · last played 3 minutes ago
        </DrawerDescription>
      </DrawerHeader>
      <div
        style={{
          padding: "4px 16px 8px",
          color: "hsl(var(--muted-foreground))",
          maxWidth: 520,
        }}
      >
        <p style={{ margin: 0 }}>
          Mira stood at the flooded threshold, lantern guttering, and listened
          to the Archive breathe beneath the tidewater. Cassius was already
          three steps ahead, as always.
        </p>
      </div>
      <DrawerFooter style={{ flexDirection: "row", gap: 12 }}>
        <Button style={{ flex: 1 }}>Continue</Button>
        <Button variant="outline" style={{ flex: 1 }}>
          Export
        </Button>
      </DrawerFooter>
    </DrawerContent>
  </Drawer>
);

// Right-side drawer — a settings panel anchored to the screen edge, showing
// the alternate direction styling (border-left, full height, no handle).
export const SettingsPanel = () => (
  <Drawer open modal={false} direction="right">
    <DrawerContent direction="right">
      <DrawerHeader>
        <DrawerTitle>Story Settings</DrawerTitle>
        <DrawerDescription>The Veil — Chapter Seven</DrawerDescription>
      </DrawerHeader>
      <div
        style={{
          padding: "4px 16px",
          color: "hsl(var(--muted-foreground))",
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Model</span>
          <span style={{ color: "hsl(var(--foreground))" }}>Opus 4.8</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Context Length</span>
          <span style={{ color: "hsl(var(--foreground))" }}>200K</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Ironman Mode</span>
          <span style={{ color: "hsl(var(--foreground))" }}>On</span>
        </div>
      </div>
      <DrawerFooter>
        <Button>Save Changes</Button>
      </DrawerFooter>
    </DrawerContent>
  </Drawer>
);
