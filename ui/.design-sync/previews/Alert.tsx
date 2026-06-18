import { Alert, AlertTitle, AlertDescription } from "nexus-ui";
import { TriangleAlert, Info } from "lucide-react";

export const Variants = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 16, width: 460 }}>
    <Alert>
      <Info className="h-4 w-4" />
      <AlertTitle>Autosave Enabled</AlertTitle>
      <AlertDescription>
        Slot 02 will checkpoint after every accepted chapter.
      </AlertDescription>
    </Alert>
    <Alert variant="destructive">
      <TriangleAlert className="h-4 w-4" />
      <AlertTitle>This Will Wipe Slot 04</AlertTitle>
      <AlertDescription>
        Starting a new story overwrites the occupied slot. This cannot be
        undone.
      </AlertDescription>
    </Alert>
  </div>
);

export const Default = () => (
  <Alert style={{ width: 460 }}>
    <Info className="h-4 w-4" />
    <AlertTitle>Continuity Check Passed</AlertTitle>
    <AlertDescription>
      No divergence detected between your input and the warm narrative slice.
    </AlertDescription>
  </Alert>
);

export const Destructive = () => (
  <Alert variant="destructive" style={{ width: 460 }}>
    <TriangleAlert className="h-4 w-4" />
    <AlertTitle>Embedding Service Unreachable</AlertTitle>
    <AlertDescription>
      The last chapter could not be committed to long-term memory. Retry before
      continuing.
    </AlertDescription>
  </Alert>
);
