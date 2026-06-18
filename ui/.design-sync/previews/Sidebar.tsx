import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuBadge,
  SidebarSeparator,
  SidebarFooter,
} from "nexus-ui";
import { BookOpen, Users, Map, Settings, Save } from "lucide-react";

// Full navigation sidebar. collapsible="none" renders the always-visible inline
// variant (no fixed offcanvas positioning), wrapped in its required provider.
export const Navigation = () => (
  <SidebarProvider style={{ minHeight: 460, height: 460 }}>
    <Sidebar collapsible="none" style={{ height: 460 }}>
      <SidebarHeader>
        <div style={{ padding: "4px 8px", fontWeight: 600, fontSize: 15 }}>
          The Veil
        </div>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Story</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton isActive>
                  <BookOpen />
                  <span>Narrative</span>
                </SidebarMenuButton>
                <SidebarMenuBadge>7</SidebarMenuBadge>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton>
                  <Users />
                  <span>Cast</span>
                </SidebarMenuButton>
                <SidebarMenuBadge>3</SidebarMenuBadge>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton>
                  <Map />
                  <span>Map</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Session</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton>
                  <Save />
                  <span>Save Slots</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton>
                  <Settings />
                  <span>Settings</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div style={{ padding: "4px 8px", fontSize: 13, opacity: 0.7 }}>
          Slot 02 · saved 3m ago
        </div>
      </SidebarFooter>
    </Sidebar>
  </SidebarProvider>
);
