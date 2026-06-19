import { Avatar, AvatarFallback } from "nexus-ui";

// Initials-only — no external portrait fetch, so captures are reproducible
// (Claude review: pravatar.cc made these environment-dependent). NEXUS
// characters frequently have no uploaded portrait, so the glyph fallback is
// the common real-world state (see CharactersPane).

export const Cast = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Avatar><AvatarFallback>MI</AvatarFallback></Avatar>
    <Avatar><AvatarFallback>CA</AvatarFallback></Avatar>
    <Avatar><AvatarFallback>AR</AvatarFallback></Avatar>
  </div>
);

export const Sizes = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Avatar style={{ width: 32, height: 32 }}><AvatarFallback>MI</AvatarFallback></Avatar>
    <Avatar style={{ width: 44, height: 44 }}><AvatarFallback>CA</AvatarFallback></Avatar>
    <Avatar style={{ width: 60, height: 60 }}><AvatarFallback>AR</AvatarFallback></Avatar>
  </div>
);

export const PartyStack = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    {["MI", "CA", "AR", "VE"].map((ini, i) => (
      <Avatar
        key={ini}
        style={{ marginLeft: i === 0 ? 0 : -12, border: "2px solid hsl(var(--background))" }}
      >
        <AvatarFallback>{ini}</AvatarFallback>
      </Avatar>
    ))}
  </div>
);
