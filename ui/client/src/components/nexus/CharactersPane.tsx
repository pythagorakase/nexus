/**
 * CharactersPane - cast roster + dossier card.
 *
 * List on the left (portrait thumbnails when uploaded, single-letter glyph
 * avatars otherwise), dossier detail on the right: portrait on a dark
 * surface behind a thin violet border (lightly sepia + cool-rotated per the
 * README imagery rules), name as a menu-font heading in natural case, and
 * prose sections from the live characters table. Hovering the portrait
 * reveals an icon-only upload affordance; uploads fail loud.
 */
import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Loader2, User } from "lucide-react";
import { DecoDivider } from "@/components/deco";
import {
  getCharacterImages,
  getCharacters,
  setMainCharacterImage,
  uploadCharacterPortrait,
} from "@/lib/narrative-api";
import type { CharacterImage, CharacterListEntry } from "@shared/schema";

interface CharactersPaneProps {
  slot: number;
}

/**
 * Root a stored portrait path as a site-absolute URL. Legacy rows stored the
 * path with a leading slash; naively prefixing "/" turned those into
 * protocol-relative URLs ("//character_portraits/...") that resolve against a
 * bogus host and render as broken images.
 */
export function portraitSrc(filePath: string): string {
  return `/${filePath.replace(/^\/+/, "")}`;
}

function DossierSection({ title, body }: { title: string; body: string | null }) {
  if (!body) return null;
  return (
    <section className="char-section">
      <span className="eyebrow">{title}</span>
      <p>{body}</p>
    </section>
  );
}

export function CharactersPane({ slot }: CharactersPaneProps) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const { data: characters, isLoading, error } = useQuery<CharacterListEntry[]>({
    queryKey: ["/api/characters", slot],
    queryFn: () => getCharacters(slot),
  });

  const selected = useMemo(() => {
    if (!characters || characters.length === 0) return null;
    return characters.find((c) => c.id === selectedId) ?? characters[0];
  }, [characters, selectedId]);

  const { data: images } = useQuery<CharacterImage[]>({
    queryKey: ["/api/characters/images", selected?.id, slot],
    queryFn: () => getCharacterImages(selected!.id, slot),
    enabled: !!selected,
  });

  const upload = useMutation({
    mutationFn: async ({
      characterId,
      file,
    }: {
      characterId: number;
      file: File;
    }) => {
      const hadImages = (images?.length ?? 0) > 0;
      const image = await uploadCharacterPortrait(characterId, slot, file);
      // The POST only marks the very first image as main; promoting each new
      // upload keeps the visible portrait in sync with what was just chosen.
      if (hadImages) {
        await setMainCharacterImage(characterId, image.id, slot);
      }
    },
    onSuccess: (_data, { characterId }) => {
      queryClient.invalidateQueries({
        queryKey: ["/api/characters/images", characterId, slot],
      });
      queryClient.invalidateQueries({ queryKey: ["/api/characters", slot] });
    },
  });

  if (isLoading) {
    return (
      <div className="pane-notice">
        <span className="notice-text">LOADING CAST…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="pane-notice">
        <span className="notice-text">[ CAST UNAVAILABLE ]</span>
        <span className="notice-detail">{(error as Error).message}</span>
      </div>
    );
  }

  if (!characters || characters.length === 0) {
    return (
      <div className="pane-notice">
        <span className="notice-text">[ NO CAST RECORDED ]</span>
        <span className="notice-detail">
          Characters appear here as the story introduces them.
        </span>
      </div>
    );
  }

  const mainImage =
    images?.find((img) => img.isMain === 1) ?? images?.[0] ?? null;

  return (
    <div className="charspane" data-testid="characters-pane">
      <div className="charspane-list">
        <ul>
          {characters.map((character) => (
            <li
              key={character.id}
              className={selected?.id === character.id ? "on" : ""}
              onClick={() => setSelectedId(character.id)}
              data-testid={`cast-member-${character.id}`}
            >
              {character.portraitPath ? (
                <img
                  className="char-glyph-img"
                  src={portraitSrc(character.portraitPath)}
                  alt=""
                />
              ) : (
                <span className="char-glyph">
                  {character.name.charAt(0).toUpperCase()}
                </span>
              )}
              <span className="char-name">{character.name}</span>
            </li>
          ))}
        </ul>
      </div>

      {selected && (
        <div className="charspane-detail">
          <div className="charspane-detail-inner">
            <header className="char-head">
              <div className="char-portrait">
                {mainImage ? (
                  <img src={portraitSrc(mainImage.filePath)} alt={selected.name} />
                ) : (
                  <User className="char-portrait-empty" size={40} />
                )}
                <button
                  type="button"
                  className="char-portrait-upload"
                  aria-label="Upload portrait"
                  disabled={upload.isPending}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {upload.isPending ? (
                    <Loader2 className="char-upload-spin" size={22} />
                  ) : (
                    <ImagePlus size={22} />
                  )}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg"
                  hidden
                  data-testid="input-portrait-file"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      upload.mutate({ characterId: selected.id, file });
                    }
                    event.target.value = "";
                  }}
                />
              </div>
              <div>
                <h2 className="char-title" data-testid="text-dossier-name">
                  {selected.name}
                </h2>
                {selected.currentLocationName && (
                  <span className="char-where">
                    at {selected.currentLocationName}
                  </span>
                )}
                {upload.isError && (
                  <span className="char-upload-error" role="alert">
                    {(upload.error as Error).message}
                  </span>
                )}
              </div>
            </header>
            <DecoDivider variant="glyph" />
            <div className="char-sections">
              <DossierSection title="Summary" body={selected.summary} />
              <DossierSection title="Appearance" body={selected.appearance} />
              <DossierSection title="Personality" body={selected.personality} />
              <DossierSection
                title="Emotional State"
                body={selected.emotionalState}
              />
              <DossierSection
                title="Current Activity"
                body={selected.currentActivity}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
