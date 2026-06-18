import {
  HoverCard,
  HoverCardTrigger,
  HoverCardContent,
  Button,
  Avatar,
  AvatarFallback,
} from "nexus-ui";

// Character dossier revealed on hover — rendered open so the content shows.
export const CharacterCard = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 140px" }}>
    <HoverCard open>
      <HoverCardTrigger asChild>
        <Button variant="link">Mira Vance</Button>
      </HoverCardTrigger>
      <HoverCardContent side="bottom">
        <div style={{ display: "flex", gap: 12 }}>
          <Avatar>
            <AvatarFallback>MV</AvatarFallback>
          </Avatar>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ fontWeight: 600 }}>Mira Vance</div>
            <p style={{ margin: 0, fontSize: 13, opacity: 0.8 }}>
              Archivist's apprentice. Last seen entering the drowned vault in
              Chapter Seven.
            </p>
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  </div>
);

// A location summary card on hover.
export const LocationCard = () => (
  <div style={{ display: "flex", justifyContent: "center", padding: "16px 24px 130px" }}>
    <HoverCard open>
      <HoverCardTrigger asChild>
        <Button variant="link">The Drowned Archive</Button>
      </HoverCardTrigger>
      <HoverCardContent side="bottom">
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontWeight: 600 }}>The Drowned Archive</div>
          <p style={{ margin: 0, fontSize: 13, opacity: 0.8 }}>
            A flooded record-hall beneath New Lisbon. Its ledgers are said to
            remember every name the tide has taken.
          </p>
          <div style={{ fontSize: 12, opacity: 0.6 }}>First visited · Chapter 3</div>
        </div>
      </HoverCardContent>
    </HoverCard>
  </div>
);
