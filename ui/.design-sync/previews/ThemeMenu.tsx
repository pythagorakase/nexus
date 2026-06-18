import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuItem,
  ThemeMenu,
  Button,
} from "nexus-ui";
import { Palette, ChevronDown } from "lucide-react";

// ThemeMenu is the shared theme-switcher fragment (label + the three theme
// items). It only renders inside an open dropdown, so we host it in one. The
// active theme (Veil) shows its check mark.
export const Open = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 220px" }}>
    <DropdownMenu open modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          <Palette style={{ width: 16, height: 16 }} /> Appearance
          <ChevronDown style={{ width: 16, height: 16 }} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" style={{ minWidth: 200 }}>
        <ThemeMenu />
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
);

// In situ: the theme items appended beneath other slot-menu entries, the way
// they appear in the real status-bar menu (a preceding item makes the leading
// separator read correctly).
export const InMenu = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 260px" }}>
    <DropdownMenu open modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          Slot 02 <ChevronDown style={{ width: 16, height: 16 }} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" style={{ minWidth: 220 }}>
        <DropdownMenuLabel>The Veil — Chapter Seven</DropdownMenuLabel>
        <DropdownMenuItem>Save Now</DropdownMenuItem>
        <DropdownMenuItem>Export Transcript</DropdownMenuItem>
        <ThemeMenu />
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
);
