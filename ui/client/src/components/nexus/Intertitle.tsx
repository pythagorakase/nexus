import { DecoDivider } from "@/components/deco";

interface IntertitleProps {
  season: number;
  episode: number;
  scene: number;
  worldLayer: string | null;
  worldTime: string | null;
  worldTimeFace: string | null;
}

/** Quiet scene grounding shown only at committed scene boundaries. */
export function Intertitle({
  season,
  episode,
  scene,
  worldLayer,
  worldTime,
  worldTimeFace,
}: IntertitleProps) {
  const layerSuffix =
    worldLayer && worldLayer !== "primary" ? ` · ${worldLayer} layer` : "";
  const slugLine = `S${String(season).padStart(2, "0")}E${String(
    episode,
  ).padStart(2, "0")} · Scene ${scene}${layerSuffix}`;

  return (
    <aside className="intertitle" data-testid="intertitle">
      <DecoDivider variant="line" className="intertitle-divider" />
      <div className="intertitle-copy">
        <div>{slugLine}</div>
        {worldTimeFace && (
          <div>
            <time dateTime={worldTime ?? undefined}>{worldTimeFace}</time>
          </div>
        )}
      </div>
    </aside>
  );
}
