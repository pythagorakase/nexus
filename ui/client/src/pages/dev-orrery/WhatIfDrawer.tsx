// What-if sandbox drawer: composes override patches in the live API shape
// (OrreryOverridesModel) and hands them up as OverrideChipEntry rows. Port of
// the prototype's "What-if drawer" region (Orrery Audit Dashboard.dc.html)
// with the mock engine's entities/places/events replaced by live props and
// /vocab data. The prototype's seeded presets and hardcoded pair-tag entry
// referenced mock entities and were dropped; pair-tag overrides are not
// exposed in v1.

import { useState } from "react";
import type { CSSProperties } from "react";

import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";

import type { ContextEntity, OverrideChipEntry, VocabPayload } from "./types";

export interface WhatIfDrawerProps {
  open: boolean;
  onClose: () => void;
  entities: { id: number; name: string }[];
  vocab: VocabPayload | null;
  needs: string[];
  onApply: (chip: OverrideChipEntry) => void;
  entityContext: (id: number) => ContextEntity | undefined;
}

const sectionLabelStyle: CSSProperties = {
  fontSize: 9,
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "hsl(var(--muted-foreground))",
};

const applyButtonStyle: CSSProperties = {
  height: 28,
  border: "1px solid hsl(var(--accent) / 0.6)",
  borderRadius: 6,
  background: "hsl(var(--accent) / 0.12)",
  color: "hsl(var(--accent))",
  fontSize: 9,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  padding: "0 12px",
  cursor: "pointer",
};

function needMaxFor(need: string): number {
  return need === "intimacy" || need === "socialize" ? 340 : 80;
}

export default function WhatIfDrawer(props: WhatIfDrawerProps) {
  const { open, onClose, entities, vocab, needs, onApply, entityContext } =
    props;

  const [entitySel, setEntitySel] = useState<string>("");
  const [need, setNeed] = useState<string>(needs[0] ?? "sleep");
  const [needVal, setNeedVal] = useState<number>(24);
  const [placeSel, setPlaceSel] = useState<string>("");
  const [eventSel, setEventSel] = useState<string>("");
  const [closeHover, setCloseHover] = useState(false);

  const entityId =
    entitySel !== "" ? Number(entitySel) : (entities[0]?.id ?? null);
  const entityName =
    entities.find((e) => e.id === entityId)?.name ??
    (entityId != null ? String(entityId) : "—");
  const ctx = entityId != null ? entityContext(entityId) : undefined;

  const needMax = needMaxFor(need);
  const needValClamped = Math.min(needVal, needMax);
  const needNowRow = ctx?.needs.find((n) => n.need_type === need);
  const needLabel = `${need} · ${
    needNowRow ? needNowRow.debt_score.toFixed(1) : "—"
  } now`;

  const placeId =
    placeSel !== "" ? Number(placeSel) : (vocab?.places[0]?.id ?? null);
  const eventType = eventSel !== "" ? eventSel : (vocab?.event_types[0]?.type ?? "");

  const onTags = new Set(
    ctx
      ? [...ctx.tags.durable, ...ctx.tags.ephemeral].map((row) => row.tag)
      : [],
  );

  const applyTag = (tag: string, ephemeral: boolean, currentlyOn: boolean) => {
    if (entityId == null) return;
    onApply({
      label: `${currentlyOn ? "−" : "+"} ${tag} @ ${entityName}`,
      patch: {
        tags: [
          {
            entity_id: entityId,
            tag,
            op: currentlyOn ? "remove" : "add",
            ephemeral,
          },
        ],
      },
    });
  };

  const applyNeed = () => {
    if (entityId == null) return;
    onApply({
      label: `${entityName}: ${need} = ${needValClamped}`,
      patch: {
        needs: [
          { entity_id: entityId, need_type: need, debt_score: needValClamped },
        ],
      },
    });
  };

  const applyMove = () => {
    if (entityId == null || placeId == null) return;
    const placeName =
      vocab?.places.find((p) => p.id === placeId)?.name ?? String(placeId);
    onApply({
      label: `move ${entityName} → ${placeName}`,
      patch: { locations: [{ entity_id: entityId, place_id: placeId }] },
    });
  };

  const applyEvent = () => {
    if (entityId == null || !eventType) return;
    onApply({
      label: `inject ${eventType} → ${entityName}`,
      patch: {
        events: [
          { event_type: eventType, target_entity_id: entityId, ticks_ago: 1 },
        ],
      },
    });
  };

  return (
    <div
      data-screen-label="What-if drawer"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: 390,
        zIndex: 40, // below shadcn portals (z-50) so Select/Command dropdowns paint above
        background: "hsl(var(--background))",
        borderLeft: "1px solid hsl(var(--accent) / 0.55)",
        boxShadow: "-14px 0 44px hsl(220 40% 2% / 0.65)",
        transform: open ? "translateX(0)" : "translateX(103%)",
        transition: "transform 0.28s cubic-bezier(0.32,0.72,0,1)",
        overflowY: "auto",
        padding: "16px 18px 30px",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <button
          onClick={onClose}
          title="Close"
          onMouseEnter={() => setCloseHover(true)}
          onMouseLeave={() => setCloseHover(false)}
          style={{
            position: "absolute",
            top: 10,
            right: 12,
            width: 24,
            height: 24,
            border: `1px solid ${
              closeHover ? "hsl(var(--accent))" : "hsl(var(--border))"
            }`,
            borderRadius: 5,
            background: "transparent",
            color: closeHover
              ? "hsl(var(--accent))"
              : "hsl(var(--muted-foreground))",
            cursor: "pointer",
            fontSize: 11,
            lineHeight: 1,
          }}
        >
          ✕
        </button>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span
            className="font-mono"
            style={{
              fontSize: 11,
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "hsl(var(--accent))",
            }}
          >
            What-if sandbox
          </span>
          <span
            style={{
              fontSize: 11.5,
              fontStyle: "italic",
              color: "hsl(var(--muted-foreground))",
            }}
          >
            Overrides copy the frozen WorldState and re-resolve live. Nothing
            canonical is written.
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="font-mono" style={sectionLabelStyle}>
            Entity
          </span>
          <Select
            value={entityId != null ? String(entityId) : ""}
            onValueChange={setEntitySel}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {entities.map((e) => (
                <SelectItem key={e.id} value={String(e.id)}>
                  {e.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="font-mono" style={sectionLabelStyle}>
            Toggle tag
          </span>
          <Command
            style={{
              border: "1px solid hsl(var(--border))",
              borderRadius: 6,
              background: "transparent",
            }}
          >
            <CommandInput placeholder="Search tag vocabulary…" />
            <CommandList style={{ maxHeight: 150 }}>
              <CommandEmpty>No tag found.</CommandEmpty>
              {(vocab?.tags ?? []).map((t) => {
                const on = onTags.has(t.tag);
                return (
                  <CommandItem
                    key={t.tag}
                    value={t.tag}
                    onSelect={() => applyTag(t.tag, t.is_ephemeral, on)}
                  >
                    <span
                      style={{
                        width: 13,
                        flex: "none",
                        color: on
                          ? "hsl(var(--chart-5))"
                          : "hsl(var(--muted-foreground) / 0.5)",
                        fontSize: 10,
                      }}
                    >
                      {on ? "●" : "○"}
                    </span>
                    <span
                      className="font-mono"
                      style={{ fontSize: 10.5, letterSpacing: "0.04em" }}
                    >
                      {t.tag}
                    </span>
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 8.5,
                        color: "hsl(var(--muted-foreground))",
                        marginLeft: "auto",
                      }}
                    >
                      {t.is_ephemeral ? "ephemeral" : "durable"}
                    </span>
                  </CommandItem>
                );
              })}
            </CommandList>
          </Command>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="font-mono" style={sectionLabelStyle}>
            Set need — {needLabel}
          </span>
          <Select
            value={need}
            onValueChange={(v) => {
              setNeed(v);
              setNeedVal((cur) => Math.min(cur, needMaxFor(v)));
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {needs.map((nd) => (
                <SelectItem key={nd} value={nd}>
                  {nd}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Slider
              value={[needValClamped]}
              min={0}
              max={needMax}
              step={1}
              onValueChange={(arr) => setNeedVal(arr[0] ?? 0)}
              style={{ flex: 1 }}
            />
            <span
              className="font-mono"
              style={{ fontSize: 11, minWidth: 34, textAlign: "right" }}
            >
              {needValClamped}
            </span>
            <button
              onClick={applyNeed}
              className="font-mono"
              style={applyButtonStyle}
            >
              set
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="font-mono" style={sectionLabelStyle}>
            Move actor
          </span>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Select
              value={placeId != null ? String(placeId) : ""}
              onValueChange={setPlaceSel}
            >
              <SelectTrigger style={{ flex: 1 }}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(vocab?.places ?? []).map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <button
              onClick={applyMove}
              className="font-mono"
              style={applyButtonStyle}
            >
              move
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="font-mono" style={sectionLabelStyle}>
            Inject recent event → {entityName}
          </span>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Select value={eventType} onValueChange={setEventSel}>
              <SelectTrigger style={{ flex: 1 }}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(vocab?.event_types ?? []).map((ev) => (
                  <SelectItem key={ev.type} value={ev.type}>
                    {ev.type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <button
              onClick={applyEvent}
              className="font-mono"
              style={applyButtonStyle}
            >
              inject
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
