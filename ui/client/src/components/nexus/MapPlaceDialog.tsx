/**
 * MapPlaceDialog - place details modal for the MapPane.
 *
 * Read-only dossier card: main image (when one exists), metadata strip
 * (type / zone / coordinates), and the long-form prose sections from the
 * places table. Image upload / gallery management is deferred (the rebuilt
 * CharactersPane is likewise read-only).
 */
import { useQuery } from "@tanstack/react-query";
import { MapPin } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DecoDivider } from "@/components/deco";
import { extractCoordinates } from "@/lib/map-geometry";
import { getPlaceImages } from "@/lib/narrative-api";
import type { Place, PlaceImage, Zone } from "@shared/schema";

interface MapPlaceDialogProps {
  place: Place | null;
  zone: Zone | null;
  slot: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * places.inhabitants arrives either as a real array or as a PG quoted
 * string ("{\"Alex\",\"Emilia\"}") depending on the driver path.
 */
function parseInhabitants(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(String).filter((entry) => entry.trim().length > 0);
  }
  if (typeof value !== "string") return [];
  const trimmed = value.trim();
  if (!trimmed) return [];
  const withoutBraces = trimmed.replace(/^[{[]|[}\]]$/g, "");
  return withoutBraces
    .split(",")
    .map((entry) => entry.trim().replace(/^"|"$/g, ""))
    .filter((entry) => entry.length > 0);
}

function DialogSection({
  title,
  body,
}: {
  title: string;
  body: string | null | undefined;
}) {
  if (!body) return null;
  return (
    <section className="char-section">
      <span className="eyebrow">{title}</span>
      <p>{body}</p>
    </section>
  );
}

export function MapPlaceDialog({
  place,
  zone,
  slot,
  open,
  onOpenChange,
}: MapPlaceDialogProps) {
  const { data: images } = useQuery<PlaceImage[]>({
    queryKey: ["/api/places", place?.id, "images", slot],
    queryFn: () => getPlaceImages(place!.id, slot),
    enabled: open && !!place,
  });

  if (!place) return null;

  const coords = extractCoordinates(place);
  const mainImage =
    images?.find((img) => img.isMain === 1) ?? images?.[0] ?? null;
  const inhabitants = parseInhabitants(place.inhabitants);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="map-dialog max-h-[85vh] overflow-y-auto"
        data-testid="map-place-dialog"
      >
        <DialogHeader>
          <span className="eyebrow brass-glow">
            <MapPin size={12} aria-hidden="true" /> PLACE
            {place.type ? ` · ${String(place.type).toUpperCase()}` : ""}
          </span>
          <DialogTitle className="map-dialog-title">{place.name}</DialogTitle>
          <DialogDescription asChild>
            <div className="map-dialog-meta">
              {zone && <span>{zone.name}</span>}
              {coords && (
                <span>
                  {coords.latitude.toFixed(6)}, {coords.longitude.toFixed(6)}
                </span>
              )}
            </div>
          </DialogDescription>
        </DialogHeader>

        {mainImage && (
          <div className="map-dialog-portrait">
            <img src={`/${mainImage.filePath}`} alt={place.name} />
          </div>
        )}

        <DecoDivider variant="glyph" />

        <div className="char-sections map-dialog-sections">
          <DialogSection title="Summary" body={place.summary} />
          <DialogSection title="History" body={place.history} />
          <DialogSection title="Current Status" body={place.currentStatus} />
          {inhabitants.length > 0 && (
            <DialogSection title="Inhabitants" body={inhabitants.join(", ")} />
          )}
          <DialogSection title="Secrets" body={place.secrets} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
