import { Calendar } from "nexus-ui";

// Single-day picker — "jump to the in-world date" of a chapter. A fixed month
// and selected day keep the capture deterministic.
export const SessionDate = () => (
  <Calendar
    mode="single"
    defaultMonth={new Date(2026, 5, 1)}
    selected={new Date(2026, 5, 18)}
    showOutsideDays
    style={{
      border: "1px solid hsl(var(--border))",
      borderRadius: 10,
      width: "fit-content",
    }}
  />
);

// Range selection — choosing a span of chapters/sessions to export.
export const ChapterRange = () => (
  <Calendar
    mode="range"
    defaultMonth={new Date(2026, 5, 1)}
    selected={{ from: new Date(2026, 5, 9), to: new Date(2026, 5, 18) }}
    showOutsideDays
    numberOfMonths={1}
    style={{
      border: "1px solid hsl(var(--border))",
      borderRadius: 10,
      width: "fit-content",
    }}
  />
);
