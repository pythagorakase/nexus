import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
  CommandShortcut,
} from "nexus-ui";
import {
  BookOpen,
  Users,
  MapPin,
  Save,
  Settings,
  Sparkles,
} from "lucide-react";

// Command palette as a quick-jump for the story engine — search input plus
// grouped, keyboard-shortcut-annotated actions. Rendered open inline.
export const QuickJump = () => (
  <Command
    style={{
      maxWidth: 440,
      border: "1px solid hsl(var(--border))",
      boxShadow: "0 12px 32px rgba(0,0,0,0.45)",
    }}
  >
    <CommandInput placeholder="Jump to a chapter, character, or place…" />
    <CommandList>
      <CommandEmpty>No matches in this story.</CommandEmpty>
      <CommandGroup heading="Navigate">
        <CommandItem>
          <BookOpen />
          <span>Go to Chapter Seven</span>
          <CommandShortcut>⌘7</CommandShortcut>
        </CommandItem>
        <CommandItem>
          <Users />
          <span>Open Cast Ledger</span>
          <CommandShortcut>⌘C</CommandShortcut>
        </CommandItem>
        <CommandItem>
          <MapPin />
          <span>Open World Map</span>
          <CommandShortcut>⌘M</CommandShortcut>
        </CommandItem>
      </CommandGroup>
      <CommandSeparator />
      <CommandGroup heading="Story">
        <CommandItem>
          <Sparkles />
          <span>Continue the Scene</span>
          <CommandShortcut>↵</CommandShortcut>
        </CommandItem>
        <CommandItem>
          <Save />
          <span>Save to Slot 02</span>
          <CommandShortcut>⌘S</CommandShortcut>
        </CommandItem>
        <CommandItem>
          <Settings />
          <span>Story Settings</span>
          <CommandShortcut>⌘,</CommandShortcut>
        </CommandItem>
      </CommandGroup>
    </CommandList>
  </Command>
);

// Filtered result — what the list looks like mid-search, with a disabled item
// for a locked slot to exercise the data-[disabled] styling.
export const CharacterSearch = () => (
  <Command
    style={{
      maxWidth: 440,
      border: "1px solid hsl(var(--border))",
      boxShadow: "0 12px 32px rgba(0,0,0,0.45)",
    }}
  >
    <CommandInput placeholder="Search characters…" />
    <CommandList>
      <CommandEmpty>No characters found.</CommandEmpty>
      <CommandGroup heading="In This Scene">
        <CommandItem>
          <Users />
          <span>Mira Vance</span>
          <CommandShortcut>POV</CommandShortcut>
        </CommandItem>
        <CommandItem>
          <Users />
          <span>Cassius Holt</span>
        </CommandItem>
        <CommandItem>
          <Users />
          <span>The Archivist</span>
        </CommandItem>
      </CommandGroup>
      <CommandSeparator />
      <CommandGroup heading="Off-Page">
        <CommandItem disabled>
          <Users />
          <span>Senator Okonkwo (not yet introduced)</span>
        </CommandItem>
      </CommandGroup>
    </CommandList>
  </Command>
);
