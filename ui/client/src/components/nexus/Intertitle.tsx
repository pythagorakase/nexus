import { DecoDivider } from "@/components/deco";

interface IntertitleProps {
  season: number;
  episode: number;
  scene: number;
  worldLayer: string | null;
  worldTime: string | null;
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

export function formatWorldTime(worldTime: string): string {
  const match = worldTime.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/,
  );
  if (!match) {
    throw new Error(`Invalid worldTime ISO timestamp: ${worldTime}`);
  }
  const [, year, month, day, hour, minute] = match;
  const monthName = MONTHS[Number(month) - 1];
  if (!monthName) {
    throw new Error(`Invalid worldTime month: ${worldTime}`);
  }
  return `${Number(day)} ${monthName} ${year} · ${hour}:${minute}`;
}

/** Quiet scene grounding shown only at committed scene boundaries. */
export function Intertitle({
  season,
  episode,
  scene,
  worldLayer,
  worldTime,
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
        {worldTime && <div>{formatWorldTime(worldTime)}</div>}
      </div>
    </aside>
  );
}
