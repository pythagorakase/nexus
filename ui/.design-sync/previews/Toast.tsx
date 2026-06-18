import {
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastAction,
  ToastClose,
} from "nexus-ui";

// Radix Toast.Root portals into its ToastViewport and renders null without one,
// so we mount a viewport but override its fixed corner positioning to flow the
// toast inline within the captured cell.
const viewportStyle: React.CSSProperties = {
  position: "static",
  width: 420,
  maxWidth: "none",
  padding: 8,
  margin: 0,
  flexDirection: "column",
  gap: 12,
};

// Default toast — a chapter-committed confirmation with an Undo action.
export const ChapterSaved = () => (
  <ToastProvider>
    <Toast open>
      <div style={{ display: "grid", gap: 4 }}>
        <ToastTitle>Chapter Committed</ToastTitle>
        <ToastDescription>
          Chapter Seven is now permanent. Ironman mode is on.
        </ToastDescription>
      </div>
      <ToastAction altText="Undo">Undo</ToastAction>
      <ToastClose />
    </Toast>
    <ToastViewport style={viewportStyle} />
  </ToastProvider>
);

// Destructive variant — a failed save with a Retry action.
export const SaveFailed = () => (
  <ToastProvider>
    <Toast open variant="destructive">
      <div style={{ display: "grid", gap: 4 }}>
        <ToastTitle>Save Failed</ToastTitle>
        <ToastDescription>
          Slot 04 is locked. Unlock it before writing the next chapter.
        </ToastDescription>
      </div>
      <ToastAction altText="Retry">Retry</ToastAction>
      <ToastClose />
    </Toast>
    <ToastViewport style={viewportStyle} />
  </ToastProvider>
);
