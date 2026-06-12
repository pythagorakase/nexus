/**
 * CharactersPane tests - cast roster minimalism and portrait resolution.
 *
 * The legacy file path below is the real save_01 assets.character_images row
 * for Alex (id 1) as of 2026-06-12: stored WITH a leading slash, which the
 * old `/${filePath}` interpolation turned into a protocol-relative URL
 * ("//character_portraits/...") and a broken image. These tests pin the fix.
 *
 * Component tests render against pre-seeded react-query caches built from
 * real row shapes (no fetch interception): data drawn from save_01.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { CharactersPane, portraitSrc } from "./CharactersPane";
import type { CharacterImage, CharacterListEntry } from "@shared/schema";

const ALEX_LEGACY_PATH = "/character_portraits/1/1759852333889_9jangr.png";

function makeCharacter(
  overrides: Partial<CharacterListEntry> & { id: number; name: string },
): CharacterListEntry {
  return {
    summary: null,
    appearance: null,
    background: null,
    personality: null,
    emotionalState: null,
    currentActivity: null,
    currentLocation: null,
    extraData: null,
    createdAt: new Date("2025-10-07T15:52:13Z"),
    updatedAt: new Date("2025-10-07T15:52:13Z"),
    currentLocationName: null,
    portraitPath: null,
    ...overrides,
  };
}

function renderPane(
  characters: CharacterListEntry[],
  imagesByCharacter: Record<number, CharacterImage[]> = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  const slot = 1;
  queryClient.setQueryData(["/api/characters", slot], characters);
  for (const character of characters) {
    queryClient.setQueryData(
      ["/api/characters/images", character.id, slot],
      imagesByCharacter[character.id] ?? [],
    );
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <CharactersPane slot={slot} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("portraitSrc", () => {
  it("roots a clean relative path", () => {
    expect(portraitSrc("character_portraits/5/abc.png")).toBe(
      "/character_portraits/5/abc.png",
    );
  });

  it("collapses the legacy leading slash instead of emitting a protocol-relative URL", () => {
    expect(portraitSrc(ALEX_LEGACY_PATH)).toBe(ALEX_LEGACY_PATH);
    expect(portraitSrc(ALEX_LEGACY_PATH)).not.toMatch(/^\/\//);
  });
});

describe("CharactersPane", () => {
  it("lists names in natural case with no location or id suffix", () => {
    renderPane([
      makeCharacter({
        id: 1,
        name: "Alex",
        currentLocation: "2",
        currentLocationName: "The Crucible",
      }),
    ]);
    const row = screen.getByTestId("cast-member-1");
    expect(row).toHaveTextContent(/^A\s*Alex$/);
    expect(within(row).queryByText(/2/)).not.toBeInTheDocument();
  });

  it("shows no CAST MEMBER eyebrow and no roster header label", () => {
    renderPane([makeCharacter({ id: 1, name: "Alex" })]);
    expect(screen.queryByText(/cast member/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^CAST\b/)).not.toBeInTheDocument();
  });

  it("renders the resolved place name as 'at {place}'", () => {
    renderPane([
      makeCharacter({
        id: 1,
        name: "Alex",
        currentLocation: "2",
        currentLocationName: "The Crucible",
      }),
    ]);
    expect(screen.getByText("at The Crucible")).toBeInTheDocument();
    expect(screen.queryByText(/currently in/i)).not.toBeInTheDocument();
  });

  it("renders no location line when the place is unknown", () => {
    renderPane([makeCharacter({ id: 2, name: "Emilia" })]);
    expect(screen.queryByText(/^at /)).not.toBeInTheDocument();
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });

  it("resolves Alex's legacy leading-slash portrait to a working src in list and detail", () => {
    renderPane(
      [
        makeCharacter({
          id: 1,
          name: "Alex",
          portraitPath: ALEX_LEGACY_PATH,
        }),
      ],
      {
        1: [
          {
            id: 1,
            characterId: 1,
            filePath: ALEX_LEGACY_PATH,
            isMain: 1,
            displayOrder: 0,
            uploadedAt: new Date("2025-10-07T15:52:13Z"),
          },
        ],
      },
    );
    const detailImg = screen.getByAltText("Alex");
    expect(detailImg).toHaveAttribute("src", ALEX_LEGACY_PATH);
    const row = screen.getByTestId("cast-member-1");
    const thumb = row.querySelector("img");
    expect(thumb).not.toBeNull();
    expect(thumb!.getAttribute("src")).toBe(ALEX_LEGACY_PATH);
  });

  it("falls back to the letter glyph in the list and offers the upload affordance", () => {
    renderPane([makeCharacter({ id: 3, name: "Pete" })]);
    const row = screen.getByTestId("cast-member-3");
    expect(within(row).getByText("P")).toBeInTheDocument();
    expect(row.querySelector("img")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Upload portrait" }),
    ).toBeInTheDocument();
  });
});
