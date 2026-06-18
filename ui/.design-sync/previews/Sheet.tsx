import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
  SheetClose,
  Button,
  Label,
} from "nexus-ui";

// Right-side settings sheet rendered open; modal={false} keeps the cell visible.
export const SettingsPanel = () => (
  <Sheet open modal={false}>
    <SheetContent side="right">
      <SheetHeader>
        <SheetTitle>Story Settings</SheetTitle>
        <SheetDescription>
          Adjust how the next chapter is generated. Changes apply on your next
          turn.
        </SheetDescription>
      </SheetHeader>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 16,
          padding: "20px 0",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <Label>Model</Label>
          <p style={{ margin: 0, fontSize: 14, opacity: 0.8 }}>
            Frontier Author
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <Label>Context Length</Label>
          <p style={{ margin: 0, fontSize: 14, opacity: 0.8 }}>
            Last twelve chapters held warm
          </p>
        </div>
      </div>
      <SheetFooter style={{ gap: 12 }}>
        <SheetClose asChild>
          <Button variant="outline">Cancel</Button>
        </SheetClose>
        <Button>Save Changes</Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>
);

// Left-side cast sheet — alternate side + a scene roster.
export const CastDrawer = () => (
  <Sheet open modal={false}>
    <SheetContent side="left">
      <SheetHeader>
        <SheetTitle>Cast in Scene</SheetTitle>
        <SheetDescription>
          Three characters are present in Chapter Seven.
        </SheetDescription>
      </SheetHeader>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 12,
          padding: "20px 0",
          fontSize: 14,
        }}
      >
        <div>Mira — drenched, counting thunder</div>
        <div>Cassius — waiting at the spire gate</div>
        <div>The Archivist — silent, watching the glass</div>
      </div>
    </SheetContent>
  </Sheet>
);
