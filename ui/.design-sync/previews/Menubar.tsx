import {
  Menubar,
  MenubarMenu,
  MenubarTrigger,
  MenubarContent,
  MenubarItem,
  MenubarSeparator,
  MenubarShortcut,
  MenubarCheckboxItem,
} from "nexus-ui";

// Application menu bar with the Story menu rendered open.
export const StoryMenu = () => (
  <div style={{ paddingBottom: 200 }}>
    <Menubar value="story">
      <MenubarMenu value="story">
        <MenubarTrigger>Story</MenubarTrigger>
        <MenubarContent>
          <MenubarItem>
            New Story <MenubarShortcut>⌘N</MenubarShortcut>
          </MenubarItem>
          <MenubarItem>
            Load Slot… <MenubarShortcut>⌘O</MenubarShortcut>
          </MenubarItem>
          <MenubarSeparator />
          <MenubarItem>
            Save Chapter <MenubarShortcut>⌘S</MenubarShortcut>
          </MenubarItem>
          <MenubarItem>Export Transcript</MenubarItem>
        </MenubarContent>
      </MenubarMenu>
      <MenubarMenu value="view">
        <MenubarTrigger>View</MenubarTrigger>
      </MenubarMenu>
      <MenubarMenu value="settings">
        <MenubarTrigger>Settings</MenubarTrigger>
      </MenubarMenu>
    </Menubar>
  </div>
);

// View menu open, showing checkable pane toggles.
export const ViewMenu = () => (
  <div style={{ paddingBottom: 200 }}>
    <Menubar value="view">
      <MenubarMenu value="story">
        <MenubarTrigger>Story</MenubarTrigger>
      </MenubarMenu>
      <MenubarMenu value="view">
        <MenubarTrigger>View</MenubarTrigger>
        <MenubarContent>
          <MenubarCheckboxItem checked>Map Pane</MenubarCheckboxItem>
          <MenubarCheckboxItem checked>Character Ledger</MenubarCheckboxItem>
          <MenubarCheckboxItem>Telemetry</MenubarCheckboxItem>
          <MenubarSeparator />
          <MenubarItem>
            Toggle Theme <MenubarShortcut>⌘⇧L</MenubarShortcut>
          </MenubarItem>
        </MenubarContent>
      </MenubarMenu>
    </Menubar>
  </div>
);
