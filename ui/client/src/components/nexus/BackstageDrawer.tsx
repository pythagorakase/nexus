import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getBackstageTurn } from "@/lib/backstage-api";
import type {
  BackstageCounts,
  BackstageKind,
  BackstageObservationRead,
  BackstageOrreryRow,
  BackstageTurnObservation,
  BackstageTurnResponse,
  ObservedCount,
} from "@/types/backstage";

const DEFAULT_BUSY_MS = 2000;
const DEFAULT_IDLE_MS = 8000;

const KIND_COLORS: Record<BackstageKind, string> = {
  character: "hsl(var(--chart-4))",
  relation: "hsl(var(--chart-1))",
  place: "hsl(var(--chart-3))",
  faction: "hsl(var(--chart-2))",
};

const BAND_COLORS: Record<string, string> = {
  crisis_constraint: "hsl(var(--chart-1))",
  embodied_maintenance: "hsl(var(--chart-2))",
  anchored_routine: "hsl(var(--chart-3))",
  affiliation: "hsl(var(--chart-4))",
  project_identity: "hsl(var(--chart-5))",
};

interface BackstageDrawerProps {
  slot: number;
  onClose: () => void;
  pollBusyMs?: number;
  pollIdleMs?: number;
}

function OrreryRows({ rows }: { rows: BackstageOrreryRow[] }) {
  return (
    <>
      {rows.map((row, index) => {
        const color = row.drive_band
          ? (BAND_COLORS[row.drive_band] ?? "hsl(var(--muted-foreground))")
          : "hsl(var(--muted-foreground))";
        const magnitude = Math.max(
          0,
          Math.min(100, (row.magnitude ?? 0) * 100),
        );
        return (
          <div
            className="nexus-backstage-orrery-row"
            data-attention={row.attention ?? undefined}
            title={[row.proposal_id, row.evaluated_at]
              .filter(Boolean)
              .join(" · ")}
            key={`${row.template_id}-${row.event_type ?? "none"}-${index}`}
          >
            <span
              className="nexus-backstage-band"
              style={{ background: color }}
            />
            {row.position != null && <span>[{row.position}]</span>}
            <span className="nexus-backstage-actor">
              {row.actor_name ?? "—"}
            </span>
            <span
              className="nexus-backstage-template"
              style={{ color }}
            >
              {row.template_id}
            </span>
            {row.target_name && (
              <span className="nexus-backstage-target">
                → {row.target_name}
              </span>
            )}
            <span className="nexus-backstage-branch">
              {row.branch_label ?? row.brief ?? ""}
            </span>
            {row.event_type && (
              <span
                className="nexus-backstage-event"
                style={{ borderColor: color, color }}
              >
                {row.event_type}
              </span>
            )}
            <span className="nexus-backstage-mag" aria-label="magnitude">
              <span style={{ width: `${magnitude}%`, background: color }} />
            </span>
          </div>
        );
      })}
    </>
  );
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value) ?? String(value);
}

function countsLine(counts: BackstageCounts): string {
  return `${counts.fired} fired · ${counts.pressures} pressures · ${counts.events} events`;
}

export function formatElapsed(seconds: number): string {
  const sign = seconds < 0 ? "−" : "+";
  const s = Math.abs(seconds);
  if (s < 3600) return `${sign}${Math.floor(s / 60)} min`;
  if (s < 86400) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${sign}${h} h${m ? ` ${m} min` : ""}`;
  }
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  return `${sign}${d} d${h ? ` ${h} h` : ""}`;
}

function tok(value: ObservedCount): string {
  return typeof value === "number" ? value.toLocaleString("en-US") : value;
}

function dur(value: number | string | null): string {
  if (typeof value === "number") return `${value.toFixed(1)}s`;
  return value === null ? "open" : value;
}

function readiness(observation: BackstageTurnObservation): string {
  if (observation.choice_ready_at === null) return "choices not ready";
  if (observation.choice_ready_at === "unknown") return "choices unknown";
  return `choices ready ${dur(observation.seconds_to_choice_ready)}`;
}

function summaryLine(observation: BackstageTurnObservation): string {
  const cp = observation.usage_totals.critical_path;
  const bg = observation.usage_totals.background;
  const providers = observation.usage_totals.overall.comparable
    ? ""
    : " · providers differ";
  return `critical ${tok(cp.input_tokens)}/${tok(cp.output_tokens)} · background ${tok(bg.input_tokens)}/${tok(bg.output_tokens)} · wall ${dur(observation.wall_time.seconds)} · ${readiness(observation)}${providers}`;
}

function ObservationBody({
  read,
  summary,
}: {
  read: BackstageObservationRead;
  summary: boolean;
}) {
  if (read.status === "unavailable") {
    return <div className="nexus-backstage-write-copy">{read.detail}</div>;
  }
  const observation = read.observation!;
  return (
    <>
      {summary && (
        <div className="nexus-backstage-write-copy">{summaryLine(observation)}</div>
      )}
      {observation.attempts.map((attempt) => (
        <div
          className="nexus-backstage-write-row"
          title={attempt.generation_session}
          key={`${attempt.generation_session}-${attempt.seat}-${attempt.attempt}`}
        >
          <span className="nexus-backstage-kind">{attempt.seat}</span>
          <span className="nexus-backstage-write-copy">
            {`#${attempt.attempt} ${attempt.model} · ${attempt.outcome ?? "open"} · window ${tok(attempt.window.input_tokens)} [${attempt.window.provenance}] · ${tok(attempt.usage.input_tokens)}/${tok(attempt.usage.output_tokens)} [${attempt.usage.provenance}]`}
          </span>
        </div>
      ))}
      {observation.jobs.entries.map((job) => (
        <div className="nexus-backstage-write-row" key={`${job.queue}-${job.id}`}>
          <span className="nexus-backstage-kind">{job.queue}</span>
          <span className="nexus-backstage-write-copy">
            {`#${job.id} · ${job.state}`}
            {job.usage && ` · ${tok(job.usage.input_tokens)}/${tok(job.usage.output_tokens)} [${job.usage.provenance}]`}
          </span>
        </div>
      ))}
      <div
        className="nexus-backstage-history"
        title={read.generation_session ?? undefined}
      >
        <span>read {observation.read_at}</span>
        <span>{observation.ledger_days_read.join(", ")}</span>
      </div>
    </>
  );
}

function SectionHeader({
  label,
  summary,
  open,
  onToggle,
  resolving = false,
}: {
  label: string;
  summary: string;
  open: boolean;
  onToggle: () => void;
  resolving?: boolean;
}) {
  return (
    <button className="nexus-backstage-section-head" onClick={onToggle}>
      <span className="nexus-backstage-chevron">{open ? "⌄" : "›"}</span>
      <span className="nexus-backstage-section-label">{label}</span>
      <span className="nexus-backstage-section-summary">{summary}</span>
      {resolving && <span className="nexus-backstage-resolving">RESOLVING</span>}
    </button>
  );
}

export function BackstageDrawer({
  slot,
  onClose,
  pollBusyMs = DEFAULT_BUSY_MS,
  pollIdleMs = DEFAULT_IDLE_MS,
}: BackstageDrawerProps) {
  const [correspondenceOpen, setCorrespondenceOpen] = useState(true);
  const [writesOpen, setWritesOpen] = useState(true);
  const [orreryOpen, setOrreryOpen] = useState(true);
  const [economicsOpen, setEconomicsOpen] = useState(true);
  const { data, error } = useQuery<BackstageTurnResponse, Error>({
    queryKey: ["/api/dev/backstage", slot, "turn"],
    queryFn: () => getBackstageTurn(slot),
    refetchInterval: (query) =>
      query.state.data?.header.skald_status === "writing"
        ? pollBusyMs
        : pollIdleMs,
    refetchIntervalInBackground: true,
  });

  const writing = data?.header.skald_status === "writing";

  return (
    <aside
      className="nexus-backstage-drawer"
      aria-label="Backstage"
      data-testid="backstage-drawer"
    >
      <header className="nexus-backstage-head">
        <span className="nexus-backstage-title">⌬ BACKSTAGE</span>
        {data && (
          <span className="nexus-backstage-turn">
            slot {String(data.header.slot).padStart(2, "0")} · {data.header.turn_label}
            {data.header.elapsed_seconds !== null && ` · ${formatElapsed(data.header.elapsed_seconds)}`}
          </span>
        )}
        <span className="nexus-backstage-head-spacer" />
        {writing && (
          <>
            <span className="nexus-backstage-live-dot" />
            <span className="nexus-backstage-live-label">SKALD WRITING</span>
          </>
        )}
        <span className="nexus-backstage-dismiss">` to dismiss</span>
        <button
          className="nexus-backstage-close"
          onClick={onClose}
          aria-label="Close Backstage"
        >
          ✕
        </button>
      </header>

      <div className="nexus-backstage-scroll">
        {error && (
          <div className="nexus-backstage-error" role="alert">
            {error.message}
          </div>
        )}
        {!data && !error && (
          <div className="nexus-backstage-loading">RECEIVING</div>
        )}
        {data && (
          <>
            <SectionHeader
              label="CORRESPONDENCE"
              summary={`${data.correspondence.exchanges.length} exchanges${data.correspondence.digest_fresh ? " · digest refreshed" : ""} · ${data.correspondence.held_threads.length} held threads`}
              open={correspondenceOpen}
              onToggle={() => setCorrespondenceOpen((open) => !open)}
            />
            {correspondenceOpen && (
              <section className="nexus-backstage-section nexus-backstage-correspondence">
                {data.correspondence.digest && (
                  <div className="nexus-backstage-digest" data-testid="backstage-digest">
                    <span className="nexus-backstage-digest-label">⚲ DIGEST · </span>
                    {data.correspondence.digest}
                  </div>
                )}
                {data.correspondence.exchanges.map((exchange) =>
                  exchange.letters.map((letter) => {
                    const gaia = letter.seat === "gaia";
                    const label =
                      letter.seat === "single_pass"
                        ? "SKALD / GAIA"
                        : gaia
                          ? "GAIA → SKALD"
                          : "SKALD → GAIA";
                    return (
                      <div
                        key={`${exchange.chunk_id}-${letter.seat}`}
                        className={`nexus-backstage-bubble ${gaia ? "gaia" : "skald"}`}
                      >
                        <div className="nexus-backstage-bubble-label">
                          {label} · {exchange.turn_label}
                        </div>
                        <div>{letter.body}</div>
                      </div>
                    );
                  }),
                )}
                {data.correspondence.held_threads.length > 0 && (
                  <div className="nexus-backstage-chips">
                    {data.correspondence.held_threads.map((thread) => (
                      <span
                        key={`${thread.template_id}-${thread.start_tick}`}
                        className="nexus-backstage-chip"
                        data-testid="backstage-held-thread"
                      >
                        {thread.template_id}
                        {thread.actor_name ? ` · ${thread.actor_name}` : ""} · seeded
                        {" "}
                        {`${thread.start_turn_label} · ${thread.streak_length} deferred · unfired`}
                      </span>
                    ))}
                  </div>
                )}
              </section>
            )}

            <SectionHeader
              label="STATE WRITES"
              summary={`${data.state_writes.rows.length} writes`}
              open={writesOpen}
              onToggle={() => setWritesOpen((open) => !open)}
            />
            {writesOpen && (
              <section className="nexus-backstage-section nexus-backstage-writes">
                {data.state_writes.rows.map((row, index) => (
                  <div
                    className="nexus-backstage-write-row"
                    key={`${row.kind}-${row.label}-${row.field}-${index}`}
                  >
                    <span
                      className="nexus-backstage-kind"
                      style={{ color: KIND_COLORS[row.kind] }}
                    >
                      {row.kind}
                    </span>
                    <span className="nexus-backstage-write-copy">
                      {row.label} · {row.operation === "bestow" && "+"}
                      {row.operation === "clear" && "−"}
                      {row.operation === "set" ? row.field : displayValue(row.field)}
                      {row.operation === "set" && row.old_value !== null
                        ? ` ${displayValue(row.old_value)} → ${displayValue(row.new_value)}`
                        : row.operation === "set"
                          ? ` = ${displayValue(row.new_value)}`
                          : ""}
                      {row.operation === "clear" && row.mechanism
                        ? ` · ${row.mechanism}`
                        : ""}
                      {row.held && <span className="nexus-backstage-held">held</span>}
                    </span>
                  </div>
                ))}
                <div className="nexus-backstage-history">
                  {data.state_writes.history.map((entry) => (
                    <span key={entry.chunk_id}>
                      {entry.turn_label} · {entry.writes} writes ▸
                    </span>
                  ))}
                </div>
              </section>
            )}

            <SectionHeader
              label="ORRERY"
              summary={`chunk ${data.header.chunk_label} · ${countsLine(data.orrery.counts)}`}
              open={orreryOpen}
              onToggle={() => setOrreryOpen((open) => !open)}
              resolving={writing}
            />
            {orreryOpen && (
              <section className="nexus-backstage-section nexus-backstage-orrery">
                <OrreryRows rows={data.orrery.rows} />
                {!!data.orrery.inventory?.length && (
                  <details className="opacity-60">
                    <summary
                      aria-label="Full ranked inventory"
                      title="Full ranked inventory"
                      className="cursor-pointer"
                    >
                      ⋯
                    </summary>
                    <OrreryRows rows={data.orrery.inventory} />
                  </details>
                )}
                <div className="nexus-backstage-orrery-foot">
                  {data.orrery.history.map((entry) => (
                    <span key={entry.chunk_id}>
                      {entry.turn_label} · {countsLine({
                        fired: entry.fired ?? 0,
                        pressures: entry.pressures ?? 0,
                        events: entry.events ?? 0,
                      })}
                    </span>
                  ))}
                  <span className="nexus-backstage-head-spacer" />
                  <a href="/dev/orrery">audit dashboard ↗</a>
                </div>
              </section>
            )}
            <SectionHeader
              label="ECONOMICS"
              summary={data.economics.accepted.status === "observed"
                ? summaryLine(data.economics.accepted.observation!)
                : "unavailable"}
              open={economicsOpen}
              onToggle={() => setEconomicsOpen((open) => !open)}
            />
            {economicsOpen && (
              <section className="nexus-backstage-section nexus-backstage-economics">
                <ObservationBody read={data.economics.accepted} summary={false} />
                {data.economics.pending !== null && (
                  <div
                    className="nexus-backstage-economics-pending"
                    data-testid="backstage-economics-pending"
                  >
                    <ObservationBody read={data.economics.pending} summary={true} />
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
      <footer className="nexus-backstage-footer">
        read-only · entries fade as turns commit · #617 exclusions untouched
      </footer>
    </aside>
  );
}
