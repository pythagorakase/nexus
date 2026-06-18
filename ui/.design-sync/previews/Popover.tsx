import {
  Popover,
  PopoverTrigger,
  PopoverContent,
  Button,
  Label,
  Input,
} from "nexus-ui";

// Settings popover with a couple of fields — rendered open and non-modal.
export const ContextSettings = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 180px" }}>
    <Popover open modal={false}>
      <PopoverTrigger asChild>
        <Button variant="outline">Context Length</Button>
      </PopoverTrigger>
      <PopoverContent side="bottom">
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontWeight: 600 }}>Context Settings</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <Label htmlFor="pop-tokens">Tokens</Label>
            <Input id="pop-tokens" type="number" defaultValue={128000} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <Label htmlFor="pop-warm">Warm Chapters</Label>
            <Input id="pop-warm" type="number" defaultValue={6} />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  </div>
);

// A confirmation-style popover with actions.
export const QuickActions = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 150px" }}>
    <Popover open modal={false}>
      <PopoverTrigger asChild>
        <Button variant="ghost">Slot 02 ⋯</Button>
      </PopoverTrigger>
      <PopoverContent side="bottom">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontWeight: 600 }}>Save Slot 02</div>
          <p style={{ margin: 0, fontSize: 13, opacity: 0.8 }}>
            The Drowned Archive — Chapter Seven
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <Button size="sm">Continue</Button>
            <Button size="sm" variant="outline">
              Load
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  </div>
);
