import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuTrigger,
  NavigationMenuContent,
  NavigationMenuLink,
} from "nexus-ui";

// Primary navigation with the Story section expanded.
export const StoryNav = () => (
  <div style={{ paddingBottom: 220 }}>
    <NavigationMenu value="story">
      <NavigationMenuList>
        <NavigationMenuItem value="story">
          <NavigationMenuTrigger>Story</NavigationMenuTrigger>
          <NavigationMenuContent>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12, width: 260 }}>
              <NavigationMenuLink style={{ padding: "8px 10px", borderRadius: 6 }}>
                <div style={{ fontWeight: 600 }}>Continue</div>
                <div style={{ fontSize: 13, opacity: 0.7 }}>Resume Chapter Seven</div>
              </NavigationMenuLink>
              <NavigationMenuLink style={{ padding: "8px 10px", borderRadius: 6 }}>
                <div style={{ fontWeight: 600 }}>Chapter Log</div>
                <div style={{ fontSize: 13, opacity: 0.7 }}>Browse all 41 chapters</div>
              </NavigationMenuLink>
            </div>
          </NavigationMenuContent>
        </NavigationMenuItem>
        <NavigationMenuItem value="world">
          <NavigationMenuTrigger>World</NavigationMenuTrigger>
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
  </div>
);

// World section expanded with map and cast links.
export const WorldNav = () => (
  <div style={{ paddingBottom: 220 }}>
    <NavigationMenu value="world">
      <NavigationMenuList>
        <NavigationMenuItem value="story">
          <NavigationMenuTrigger>Story</NavigationMenuTrigger>
        </NavigationMenuItem>
        <NavigationMenuItem value="world">
          <NavigationMenuTrigger>World</NavigationMenuTrigger>
          <NavigationMenuContent>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12, width: 260 }}>
              <NavigationMenuLink style={{ padding: "8px 10px", borderRadius: 6 }}>
                <div style={{ fontWeight: 600 }}>Map</div>
                <div style={{ fontSize: 13, opacity: 0.7 }}>New Lisbon and the drowned coast</div>
              </NavigationMenuLink>
              <NavigationMenuLink style={{ padding: "8px 10px", borderRadius: 6 }}>
                <div style={{ fontWeight: 600 }}>Cast</div>
                <div style={{ fontSize: 13, opacity: 0.7 }}>Mira · Cassius · The Archivist</div>
              </NavigationMenuLink>
            </div>
          </NavigationMenuContent>
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
  </div>
);
