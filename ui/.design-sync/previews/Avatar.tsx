import { Avatar, AvatarImage, AvatarFallback } from "nexus-ui";

export const Cast = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Avatar>
      <AvatarImage src="https://i.pravatar.cc/80?img=47" alt="Mira" />
      <AvatarFallback>MI</AvatarFallback>
    </Avatar>
    <Avatar>
      <AvatarImage src="https://i.pravatar.cc/80?img=12" alt="Cassius" />
      <AvatarFallback>CA</AvatarFallback>
    </Avatar>
    <Avatar>
      <AvatarImage src="https://i.pravatar.cc/80?img=32" alt="The Archivist" />
      <AvatarFallback>AR</AvatarFallback>
    </Avatar>
  </div>
);

export const Fallbacks = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Avatar>
      <AvatarFallback>MI</AvatarFallback>
    </Avatar>
    <Avatar>
      <AvatarFallback>CA</AvatarFallback>
    </Avatar>
    <Avatar>
      <AvatarFallback>AR</AvatarFallback>
    </Avatar>
  </div>
);

export const PartyStack = () => (
  <div style={{ display: "flex", alignItems: "center" }}>
    {[47, 12, 32, 5].map((img, i) => (
      <Avatar key={img} style={{ marginLeft: i === 0 ? 0 : -12 }}>
        <AvatarImage src={`https://i.pravatar.cc/80?img=${img}`} alt="" />
        <AvatarFallback>{["MI", "CA", "AR", "VE"][i]}</AvatarFallback>
      </Avatar>
    ))}
  </div>
);
