import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
  Button,
} from "nexus-ui";

export const IronmanHint = () => (
  <TooltipProvider>
    <div style={{ display: "flex", justifyContent: "center", padding: "48px 24px" }}>
      <Tooltip open>
        <TooltipTrigger asChild>
          <Button variant="outline">Ironman Mode</Button>
        </TooltipTrigger>
        <TooltipContent side="top">
          Chapters commit permanently — no rewinding once accepted.
        </TooltipContent>
      </Tooltip>
    </div>
  </TooltipProvider>
);

export const SlotInfo = () => (
  <TooltipProvider>
    <div style={{ display: "flex", justifyContent: "center", padding: "24px 24px 48px" }}>
      <Tooltip open>
        <TooltipTrigger asChild>
          <Button variant="ghost">Slot 02</Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          The Veil — Chapter Seven · last saved 3 minutes ago
        </TooltipContent>
      </Tooltip>
    </div>
  </TooltipProvider>
);
