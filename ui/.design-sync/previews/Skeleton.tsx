import { Skeleton } from "nexus-ui";

// Loading state shaped like a save-slot card: avatar + title lines + prose + footer buttons.
export const SlotCardLoading = () => (
  <div
    style={{
      width: 360,
      border: "1px solid hsl(var(--border))",
      borderRadius: 12,
      padding: 20,
      display: "flex",
      flexDirection: "column",
      gap: 16,
    }}
  >
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <Skeleton style={{ height: 44, width: 44, borderRadius: 9999 }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
        <Skeleton style={{ height: 16, width: "55%" }} />
        <Skeleton style={{ height: 12, width: "35%" }} />
      </div>
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <Skeleton style={{ height: 12, width: "100%" }} />
      <Skeleton style={{ height: 12, width: "92%" }} />
      <Skeleton style={{ height: 12, width: "78%" }} />
    </div>
    <div style={{ display: "flex", gap: 12 }}>
      <Skeleton style={{ height: 36, width: 110, borderRadius: 8 }} />
      <Skeleton style={{ height: 36, width: 90, borderRadius: 8 }} />
    </div>
  </div>
);

// A short list of loading rows — the cast pane while it fetches.
export const CastListLoading = () => (
  <div style={{ width: 320, display: "flex", flexDirection: "column", gap: 14 }}>
    {[0, 1, 2].map((i) => (
      <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Skeleton style={{ height: 36, width: 36, borderRadius: 9999 }} />
        <div
          style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}
        >
          <Skeleton style={{ height: 12, width: "60%" }} />
          <Skeleton style={{ height: 10, width: "40%" }} />
        </div>
      </div>
    ))}
  </div>
);
