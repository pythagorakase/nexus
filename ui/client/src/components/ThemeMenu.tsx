import { Sparkles, Monitor, Wand2 } from "lucide-react";
import {
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/contexts/ThemeContext";

/**
 * Shared theme menu items for dropdown menus.
 * Used by both StatusBar and WizardShell to provide consistent theme switching.
 */
export function ThemeMenu() {
  const { theme, setTheme } = useTheme();

  return (
    <>
      <DropdownMenuSeparator />
      <DropdownMenuLabel className="text-xs text-muted-foreground">
        Theme
      </DropdownMenuLabel>
      <DropdownMenuItem onClick={() => setTheme("gilded")}>
        <div className="flex items-center gap-2 cursor-pointer">
          <Sparkles className="h-4 w-4" />
          <span>Gilded{theme === "gilded" ? " ✓" : ""}</span>
        </div>
      </DropdownMenuItem>
      <DropdownMenuItem onClick={() => setTheme("vector")}>
        <div className="flex items-center gap-2 cursor-pointer">
          <Monitor className="h-4 w-4" />
          <span>Vector{theme === "vector" ? " ✓" : ""}</span>
        </div>
      </DropdownMenuItem>
      <DropdownMenuItem onClick={() => setTheme("veil")}>
        <div className="flex items-center gap-2 cursor-pointer">
          <Wand2 className="h-4 w-4" />
          <span>Veil{theme === "veil" ? " ✓" : ""}</span>
        </div>
      </DropdownMenuItem>
    </>
  );
}
