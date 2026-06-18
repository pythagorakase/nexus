import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuGroup,
  Button,
} from "nexus-ui";
import { Settings2, Save, Download, Trash2, ChevronDown } from "lucide-react";

// Slot actions menu, rendered open beneath its trigger. Items + shortcuts +
// a destructive action, plus padding so the portalled panel lands in-frame.
export const SlotActions = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 220px" }}>
    <DropdownMenu open modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          Slot 02 <ChevronDown style={{ width: 16, height: 16 }} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" style={{ minWidth: 220 }}>
        <DropdownMenuLabel>The Veil — Chapter Seven</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem>
            <Save />
            <span>Save Now</span>
            <DropdownMenuShortcut>⌘S</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Download />
            <span>Export Transcript</span>
            <DropdownMenuShortcut>⌘E</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Settings2 />
            <span>Story Settings</span>
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem>
          <Trash2 />
          <span>Wipe Slot</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
);

// Story-options menu exercising checkbox + radio item indicators.
export const ViewOptions = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 240px" }}>
    <DropdownMenu open modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          Narration <ChevronDown style={{ width: 16, height: 16 }} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" style={{ minWidth: 220 }}>
        <DropdownMenuLabel>Display</DropdownMenuLabel>
        <DropdownMenuCheckboxItem checked>
          Typewriter Effect
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem checked={false}>
          Show Inline Choices
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Pacing</DropdownMenuLabel>
        <DropdownMenuRadioGroup value="measured">
          <DropdownMenuRadioItem value="brisk">Brisk</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="measured">
            Measured
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="lingering">
            Lingering
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
);
