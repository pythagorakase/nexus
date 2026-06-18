import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
  Button,
} from "nexus-ui";
import { ChevronDown } from "lucide-react";

// Open disclosure — a chapter's hidden cast/notes revealed inline.
export const ChapterNotes = () => (
  <Collapsible defaultOpen style={{ width: 380 }}>
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-serif, Georgia, serif)",
          fontSize: 16,
          color: "hsl(var(--foreground))",
        }}
      >
        Chapter Seven — Notes
      </span>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm">
          <ChevronDown style={{ width: 16, height: 16 }} />
        </Button>
      </CollapsibleTrigger>
    </div>
    <CollapsibleContent>
      <div
        style={{
          marginTop: 10,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {[
          "Mira learns the Archivist's true name.",
          "Cassius withholds the tide schedule — first betrayal beat.",
          "Establish the flooded lower stacks for Chapter Nine payoff.",
        ].map((note) => (
          <div
            key={note}
            style={{
              borderRadius: 8,
              border: "1px solid hsl(var(--border))",
              padding: "10px 12px",
              fontSize: 13,
              color: "hsl(var(--muted-foreground))",
            }}
          >
            {note}
          </div>
        ))}
      </div>
    </CollapsibleContent>
  </Collapsible>
);

// Collapsed state — same primitive, trigger shows the summary while content
// stays tucked away.
export const WorldDetail = () => (
  <Collapsible style={{ width: 380 }}>
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={{ fontSize: 15, color: "hsl(var(--foreground))" }}>
          The Veil — World Rules
        </span>
        <span style={{ fontSize: 12, color: "hsl(var(--muted-foreground))" }}>
          6 rules · collapsed
        </span>
      </div>
      <CollapsibleTrigger asChild>
        <Button variant="outline" size="sm">
          Expand
        </Button>
      </CollapsibleTrigger>
    </div>
    <CollapsibleContent>
      <div
        style={{
          marginTop: 10,
          borderRadius: 8,
          border: "1px solid hsl(var(--border))",
          padding: "10px 12px",
          fontSize: 13,
          color: "hsl(var(--muted-foreground))",
        }}
      >
        Tidewater magic only works below the high-water line.
      </div>
    </CollapsibleContent>
  </Collapsible>
);
