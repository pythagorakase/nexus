import { useEffect, useRef } from "react";
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuCheckboxItem,
  ContextMenuRadioGroup,
  ContextMenuRadioItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuSub,
  ContextMenuSubTrigger,
  ContextMenuSubContent,
} from "nexus-ui";

// Radix ContextMenu positions its content from the pointer event that opens
// it; a controlled `open` alone never anchors. Firing a real `contextmenu`
// event on the trigger after mount opens AND positions the menu so the static
// capture shows the live panel.
function useOpenContextMenu(x: number, y: number) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.dispatchEvent(
      new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
        clientX: r.left + x,
        clientY: r.top + y,
      })
    );
  }, [x, y]);
  return ref;
}

const triggerBox: React.CSSProperties = {
  border: "1px dashed hsl(var(--border))",
  borderRadius: 8,
  padding: "18px 20px",
  color: "hsl(var(--muted-foreground))",
  maxWidth: 360,
};

// Right-click menu on a chapter row. Items + shortcuts + a nested submenu.
export const ChapterActions = () => {
  const ref = useOpenContextMenu(40, 36);
  return (
    <div style={{ padding: "24px 24px 220px" }}>
      <ContextMenu>
        <ContextMenuTrigger ref={ref} style={triggerBox}>
          Chapter Seven — "The Drowned Archive"
        </ContextMenuTrigger>
        <ContextMenuContent style={{ minWidth: 220 }}>
          <ContextMenuLabel>Chapter Seven</ContextMenuLabel>
          <ContextMenuSeparator />
          <ContextMenuItem>
            Continue Scene
            <ContextMenuShortcut>↵</ContextMenuShortcut>
          </ContextMenuItem>
          <ContextMenuItem>
            Rewind to Here
            <ContextMenuShortcut>⌘R</ContextMenuShortcut>
          </ContextMenuItem>
          <ContextMenuSub>
            <ContextMenuSubTrigger>Insert</ContextMenuSubTrigger>
            <ContextMenuSubContent>
              <ContextMenuItem>Narrator Aside</ContextMenuItem>
              <ContextMenuItem>Time Skip</ContextMenuItem>
              <ContextMenuItem>New Character</ContextMenuItem>
            </ContextMenuSubContent>
          </ContextMenuSub>
          <ContextMenuSeparator />
          <ContextMenuItem>
            Delete Chapter
            <ContextMenuShortcut>⌫</ContextMenuShortcut>
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>
    </div>
  );
};

// Cast-entry menu exercising checkbox + radio indicators.
export const CharacterActions = () => {
  const ref = useOpenContextMenu(40, 36);
  return (
    <div style={{ padding: "24px 24px 220px" }}>
      <ContextMenu>
        <ContextMenuTrigger ref={ref} style={triggerBox}>
          Mira Vance — Protagonist
        </ContextMenuTrigger>
        <ContextMenuContent style={{ minWidth: 220 }}>
          <ContextMenuLabel>Mira Vance</ContextMenuLabel>
          <ContextMenuSeparator />
          <ContextMenuCheckboxItem checked>
            Track in Ledger
          </ContextMenuCheckboxItem>
          <ContextMenuCheckboxItem checked={false}>
            Pin to Sidebar
          </ContextMenuCheckboxItem>
          <ContextMenuSeparator />
          <ContextMenuLabel inset>Point of View</ContextMenuLabel>
          <ContextMenuRadioGroup value="mira">
            <ContextMenuRadioItem value="mira">
              Mira Vance
            </ContextMenuRadioItem>
            <ContextMenuRadioItem value="cassius">
              Cassius Holt
            </ContextMenuRadioItem>
            <ContextMenuRadioItem value="omniscient">
              Omniscient
            </ContextMenuRadioItem>
          </ContextMenuRadioGroup>
        </ContextMenuContent>
      </ContextMenu>
    </div>
  );
};
