import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/toaster";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { InteractiveWizard, type WizardResumeData } from "./InteractiveWizard";

const STATUS_URL = "/api/story/new/retrograde/status?slot=5";

// The saved wizard is ready: the introduction artifact awaits confirmation,
// and confirming it starts the transition the wait screen tracks.
const readyWizard: WizardResumeData = {
    thread_id: "conv_ready",
    current_phase: "ready",
    messages: [{ role: "assistant", content: "Your story is ready to begin." }],
    choices: [],
    setting_draft: { world_name: "The Glass Orchard" },
    character_draft: null,
    character_state: null,
    selected_seed: { title: "The Orchard Gate", hook: "Rain needles the glass." },
    layer_draft: { name: "Verdance" },
    zone_draft: { name: "Lower Terraces" },
    initial_location: { name: "Orchard Gate" },
};

interface Deferred {
    resolve: (response: Response) => void;
}

/**
 * A stand-in gateway at the fetch boundary. Status reads answer with the
 * current `status`; the transition and bootstrap requests stay in flight until
 * the test settles them, and reject like fetch when their signal aborts.
 */
function stubGateway() {
    const gateway = {
        status: { slot: 5, stage: "idle", stages: [] } as Record<string, unknown>,
        statusFailure: null as Response | null,
        statusReads: 0,
        served: [] as unknown[],
        requests: [] as string[],
        transition: null as Deferred | null,
        bootstrap: null as Deferred | null,
    };
    const pending = (key: "transition" | "bootstrap", signal?: AbortSignal | null) =>
        new Promise<Response>((resolve, reject) => {
            gateway[key] = { resolve };
            signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        });
    const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        gateway.requests.push(`${init?.method ?? "GET"} ${url}`);
        if (url === "/api/settings") {
            return Response.json({ orrery: { retrograde: { wizard: { status_poll_interval_seconds: 0.01 } } } });
        }
        if (url === STATUS_URL) {
            gateway.statusReads += 1;
            gateway.served.push(gateway.status.stage);
            return gateway.statusFailure ?? Response.json(gateway.status);
        }
        if (url === "/api/story/new/transition") return pending("transition", init?.signal);
        if (url === "/api/narrative/continue") return pending("bootstrap", init?.signal);
        throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    return gateway;
}

function stage(name: string, detail: Record<string, unknown> = {}) {
    return { slot: 5, stage: name, detail, updated_at: "2026-09-26T12:00:00+00:00", stages: [] };
}

const IDLE = { slot: 5, stage: "idle", stages: [] };
const TRANSITIONED = { status: "transitioned", retrograde: { enabled: true } };

function renderReadyWizard(onComplete = vi.fn()) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    queryClient.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
    queryClient.setQueryData(["/api/preferences"], { theme: "veil" });
    const view = render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider>
                <InteractiveWizard
                    slot={5}
                    onComplete={onComplete}
                    onCancel={vi.fn()}
                    onResumeRequired={vi.fn()}
                    onPhaseChange={vi.fn()}
                    wizardData={{}}
                    setWizardData={vi.fn()}
                    resumeData={readyWizard}
                    initialPhase="seed"
                />
                <Toaster />
            </ThemeProvider>
        </QueryClientProvider>,
    );
    return { ...view, onComplete };
}

async function confirmIntroduction() {
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));
}

const pipStates = () => screen.getAllByTestId("wait-stage").map((pip) => pip.getAttribute("data-state"));
const track = (active: number, last = "active") =>
    Array.from({ length: 6 }, (_, index) => (index < active ? "done" : index === active ? last : "pending"));

/** Poll reads settle quickly (10 ms interval); prove none follow. */
async function expectNoFurtherStatusReads(gateway: ReturnType<typeof stubGateway>) {
    const reads = gateway.statusReads;
    await act(() => new Promise((resolve) => setTimeout(resolve, 80)));
    expect(gateway.statusReads).toBe(reads);
}

afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe("genesis stage waiter", () => {
    it("tracks each stage while the transition is in flight, then glows bootstrap until the session returns", async () => {
        const gateway = stubGateway();
        const { onComplete } = renderReadyWizard();
        await confirmIntroduction();

        await waitFor(() => expect(gateway.transition).not.toBeNull());
        expect(gateway.requests.slice(0, 2)).toEqual(["GET /api/settings", "POST /api/story/new/transition"]);
        await waitFor(() => expect(gateway.statusReads).toBeGreaterThan(0));
        expect(pipStates()).toEqual(Array(6).fill("pending"));

        gateway.status = stage("packet");
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
        gateway.status = stage("expansion", { candidates: 6, selected: 3 });
        await waitFor(() => expect(pipStates()).toEqual(track(2)));
        gateway.status = stage("embedding", { pending_summaries: 4 });
        await waitFor(() => expect(pipStates()).toEqual(track(4)));
        expect(document.body.textContent).not.toMatch(/%/);

        // "done" is terminal: reads stop although the response has not arrived.
        gateway.status = stage("done", { embedded_summaries: 4 });
        await waitFor(() => expect(gateway.served.at(-1)).toBe("done"));
        await expectNoFurtherStatusReads(gateway);
        expect(pipStates()).toEqual(track(4));

        await act(async () => gateway.transition!.resolve(Response.json(TRANSITIONED)));
        await waitFor(() => expect(pipStates()).toEqual(track(5)));
        expect(screen.getByText("Starting narrative generation...")).toBeInTheDocument();
        expect(gateway.requests.at(-1)).toBe("POST /api/narrative/continue");
        expect(onComplete).not.toHaveBeenCalled();

        await act(async () => gateway.bootstrap!.resolve(Response.json({ session_id: "opening-session" })));
        await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
        expect(JSON.parse(localStorage.getItem("pendingBootstrapSession")!)).toMatchObject({
            slot: 5,
            sessionId: "opening-session",
        });
        expect(screen.queryAllByTestId("wait-stage")).toHaveLength(0);
        await expectNoFurtherStatusReads(gateway);
    });

    it("stops reading once the transition settles", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        gateway.status = stage("seed_candidates", { weird: "medium" });
        await waitFor(() => expect(pipStates()).toEqual(track(1)));

        await act(async () => gateway.transition!.resolve(Response.json(TRANSITIONED)));
        await waitFor(() => expect(pipStates()).toEqual(track(5)));
        await expectNoFurtherStatusReads(gateway);
    });

    it("marks the stage the gateway recorded as failed and keeps the error with Retry and Cancel", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        gateway.status = stage("expansion", { candidates: 6, selected: 3 });
        await waitFor(() => expect(pipStates()).toEqual(track(2)));

        // The world writes failed before persistence began: only the
        // gateway's failure record names the stage.
        gateway.status = stage("failed", { stage: "persistence" });
        vi.spyOn(console, "error").mockImplementation(() => {});
        const readsBeforeFailure = gateway.statusReads;
        await act(async () =>
            gateway.transition!.resolve(Response.json({ detail: "Retrograde persistence blocked: 2 unresolved refs" }, { status: 400 })),
        );

        expect(await screen.findByText("Retrograde persistence blocked: 2 unresolved refs")).toBeInTheDocument();
        expect(pipStates()).toEqual(track(3, "failed"));
        expect(screen.getByText("Generation Failed")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
        expect(gateway.statusReads).toBeGreaterThan(readsBeforeFailure);
        await expectNoFurtherStatusReads(gateway);

        // Retry starts a fresh run from an empty track.
        gateway.status = IDLE;
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        await waitFor(() => expect(pipStates()).toEqual(Array(6).fill("pending")));
        expect(screen.queryByText("Generation Failed")).toBeNull();
        gateway.status = stage("packet");
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
    });

    it("stops reading when the run reports failed while the response is still in flight", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        // The run reports idle from its reset before it can fail.
        await waitFor(() => expect(gateway.served).toContain("idle"));
        gateway.status = stage("failed", { stage: "embedding" });
        await waitFor(() => expect(pipStates()).toEqual(track(4)));
        await expectNoFurtherStatusReads(gateway);
    });

    it("reads past the previous run's failure record until this run reports", async () => {
        const gateway = stubGateway();
        // Retry's first reads can precede the new run's reset of the record.
        gateway.status = stage("failed", { stage: "persistence" });
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.statusReads).toBeGreaterThan(2));
        expect(pipStates()).toEqual(Array(6).fill("pending"));

        gateway.status = IDLE;
        await waitFor(() => expect(gateway.served.at(-1)).toBe("idle"));
        gateway.status = stage("packet");
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
    });

    it("marks no stage failed when the transition is refused before its run starts", async () => {
        const gateway = stubGateway();
        gateway.status = stage("failed", { stage: "persistence" });
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.transition).not.toBeNull());
        vi.spyOn(console, "error").mockImplementation(() => {});
        const readsBeforeRefusal = gateway.statusReads;
        await act(async () =>
            gateway.transition!.resolve(
                Response.json({ detail: "Confirm the setting and character before starting the story." }, { status: 409 }),
            ),
        );
        expect(await screen.findByText("Confirm the setting and character before starting the story.")).toBeInTheDocument();
        expect(gateway.statusReads).toBeGreaterThan(readsBeforeRefusal);
        expect(pipStates()).toEqual(Array(6).fill("pending"));
    });

    it("leaves a skipped Retrograde run's pips dim while bootstrap glows", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.served).toContain("idle"));
        await act(async () =>
            gateway.transition!.resolve(
                Response.json({ status: "transitioned", retrograde: { enabled: false, skip_reason: "mock_wizard_model" } }),
            ),
        );
        await waitFor(() => expect(pipStates()).toEqual([...Array(5).fill("skipped"), "active"]));
    });

    it("reports a transition response that names no Retrograde outcome", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.transition).not.toBeNull());
        vi.spyOn(console, "error").mockImplementation(() => {});
        await act(async () => gateway.transition!.resolve(Response.json({ status: "transitioned" })));
        expect(
            await screen.findByText('Transition response names no Retrograde outcome: {"status":"transitioned"}'),
        ).toBeInTheDocument();
        expect(gateway.bootstrap).toBeNull();
    });

    it("leaves every pip dim when the transition fails before the first stage", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.transition).not.toBeNull());
        vi.spyOn(console, "error").mockImplementation(() => {});
        await act(async () =>
            gateway.transition!.resolve(Response.json({ detail: "Incomplete setup data. Missing: zone" }, { status: 422 })),
        );
        expect(await screen.findByText("Incomplete setup data. Missing: zone")).toBeInTheDocument();
        expect(pipStates()).toEqual(Array(6).fill("pending"));
    });

    it("keeps the transition error and adds the stage-read error when the failure record is unreadable", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        gateway.status = stage("seed_candidates", { weird: "medium" });
        await waitFor(() => expect(pipStates()).toEqual(track(1)));
        vi.spyOn(console, "error").mockImplementation(() => {});
        gateway.statusFailure = new Response("Gateway worker restarted", { status: 502 });
        await act(async () =>
            gateway.transition!.resolve(Response.json({ detail: "Transition failed: provider timeout" }, { status: 500 })),
        );
        const alert = await screen.findByText(/Transition failed: provider timeout/);
        expect(alert).toHaveTextContent("502: Gateway worker restarted");
        expect(screen.getByText("Generation Failed")).toBeInTheDocument();
        expect(pipStates()).toEqual(track(1, "failed"));
    });

    it("fails the bootstrap stage when the opening narrative cannot be scheduled", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.transition).not.toBeNull());
        await act(async () => gateway.transition!.resolve(Response.json(TRANSITIONED)));
        await waitFor(() => expect(gateway.bootstrap).not.toBeNull());
        vi.spyOn(console, "error").mockImplementation(() => {});
        await act(async () =>
            gateway.bootstrap!.resolve(Response.json({ detail: "Opening generation unavailable" }, { status: 503 })),
        );
        expect(await screen.findByText("Opening generation unavailable")).toBeInTheDocument();
        expect(pipStates()).toEqual(track(5, "failed"));
    });

    it("stops reading when the player cancels", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        gateway.status = stage("packet");
        await waitFor(() => expect(pipStates()).toEqual(track(0)));

        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        await waitFor(() => expect(screen.queryAllByTestId("wait-stage")).toHaveLength(0));
        await expectNoFurtherStatusReads(gateway);
    });

    it("stops reading when the wizard unmounts", async () => {
        const gateway = stubGateway();
        const { unmount } = renderReadyWizard();
        await confirmIntroduction();
        gateway.status = stage("packet");
        await waitFor(() => expect(pipStates()).toEqual(track(0)));

        unmount();
        await expectNoFurtherStatusReads(gateway);
    });

    it("reports a failed stage read loudly and stops reading while the transition continues", async () => {
        const gateway = stubGateway();
        const { onComplete } = renderReadyWizard();
        vi.spyOn(console, "error").mockImplementation(() => {});
        gateway.statusFailure = new Response("Gateway worker restarted", { status: 502 });
        await confirmIntroduction();

        expect(await screen.findByText("502: Gateway worker restarted")).toBeInTheDocument();
        expect(screen.getByText("Transmission Error")).toBeInTheDocument();
        await expectNoFurtherStatusReads(gateway);

        await act(async () => gateway.transition!.resolve(Response.json(TRANSITIONED)));
        await waitFor(() => expect(gateway.bootstrap).not.toBeNull());
        await act(async () => gateway.bootstrap!.resolve(Response.json({ session_id: "opening-session" })));
        await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    });

    it("reports a missing poll interval instead of guessing one", async () => {
        const gateway = stubGateway();
        vi.mocked(fetch).mockImplementationOnce(async () => Response.json({ orrery: {} }));
        vi.spyOn(console, "error").mockImplementation(() => {});
        renderReadyWizard();
        await confirmIntroduction();
        expect(
            await screen.findByText(
                "nexus.toml [orrery.retrograde.wizard] status_poll_interval_seconds must be a positive number",
            ),
        ).toBeInTheDocument();
        expect(gateway.transition).toBeNull();
        expect(gateway.statusReads).toBe(0);
    });
});
