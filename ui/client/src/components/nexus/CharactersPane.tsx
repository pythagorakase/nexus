/**
 * CharactersPane - cast roster + dossier card.
 *
 * List on the left (single-letter glyph avatars, menu-font names), dossier
 * detail on the right: portrait on a dark surface behind a thin violet
 * border (lightly sepia + cool-rotated per the README imagery rules),
 * name as a menu-font heading, and prose sections from the live
 * characters table.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { User } from "lucide-react";
import { DecoDivider } from "@/components/deco";
import { getCharacterImages, getCharacters } from "@/lib/narrative-api";
import type { Character, CharacterImage } from "@shared/schema";

interface CharactersPaneProps {
  slot: number;
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

  const { data: characters, isLoading, error } = useQuery<Character[]>({
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
        <span className="eyebrow brass-glow">CAST · {characters.length}</span>
        <ul>
          {characters.map((character) => (
            <li
              key={character.id}
              className={selected?.id === character.id ? "on" : ""}
              onClick={() => setSelectedId(character.id)}
              data-testid={`cast-member-${character.id}`}
            >
              <span className="char-glyph">
                {character.name.charAt(0).toUpperCase()}
              </span>
              <span className="char-name">{character.name}</span>
              {character.currentLocation && (
                <span className="char-role">· {character.currentLocation}</span>
              )}
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
                  <img src={`/${mainImage.filePath}`} alt={selected.name} />
                ) : (
                  <User className="char-portrait-empty" size={40} />
                )}
              </div>
              <div>
                <span className="eyebrow">CAST MEMBER</span>
                <h2 className="char-title" data-testid="text-dossier-name">
                  {selected.name}
                </h2>
                {selected.currentLocation && (
                  <span className="caption">
                    currently in {selected.currentLocation}
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
