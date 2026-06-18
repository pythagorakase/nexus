import {
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
} from "nexus-ui";

// Toaster is the app's mount point: a ToastProvider + ToastViewport that renders
// whatever toasts are pushed via the imperative hook (which can't fire in a
// static preview). We mirror that exact shell with two visible toasts to show a
// realistic stacked notification state. The viewport's fixed corner positioning
// is overridden so the stack flows inside the captured cell.
const viewportStyle: React.CSSProperties = {
  position: "static",
  width: 420,
  maxWidth: "none",
  padding: 8,
  margin: 0,
  flexDirection: "column",
  gap: 12,
};

export const NotificationStack = () => (
  <ToastProvider>
    <Toast open>
      <div style={{ display: "grid", gap: 4 }}>
        <ToastTitle>Chapter Committed</ToastTitle>
        <ToastDescription>Chapter Seven is now permanent.</ToastDescription>
      </div>
      <ToastClose />
    </Toast>
    <Toast open variant="destructive">
      <div style={{ display: "grid", gap: 4 }}>
        <ToastTitle>Slot Locked</ToastTitle>
        <ToastDescription>Unlock Slot 04 before saving again.</ToastDescription>
      </div>
      <ToastClose />
    </Toast>
    <ToastViewport style={viewportStyle} />
  </ToastProvider>
);
