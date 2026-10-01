import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/ui/toaster";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { InteractiveWizard, type WizardResumeData } from "./InteractiveWizard";

const STATUS_URL = "/api/story/new/retrograde/status?slot=5";
// Run identities: the gateway starts each transition run's record under a
// new one, replacing the previous run's record.
const PREVIOUS_RUN = "run-before-this-transition";
const THIS_RUN = "run-of-this-transition";
const RETRY_RUN = "run-of-the-retry";

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
 * A stand-in player-plane gateway at the fetch boundary. Status reads answer
 * with the current `status` record plus the configured poll interval, as the
 * gateway does; the operator-only settings route is not served. The
 * transition and bootstrap requests stay in flight until the test settles
 * them, and reject like fetch when their signal aborts.
 */
function stubGateway() {
    const gateway = {
        status: NO_RUN as Record<string, unknown>,
        // nexus.toml's status_poll_interval_seconds as each status reports it.
        pollSeconds: 0.01 as number | undefined,
        // Every status read fails while set; failedReads names single reads
        // (counted from 1) that fail.
        statusFailing: false,
        failedReads: new Set<number>(),
        statusReads: 0,
        served: [] as unknown[],
        requests: [] as string[],
        // JSON bodies of the transition posts and strangeness saves, in order.
        transitionBodies: [] as unknown[],
        weirdSaves: [] as unknown[],
        // How the gateway answers a strangeness save; it echoes by default.
        weirdAnswer: (body: { slot: number; weird_level: string }): Response | Promise<Response> =>
            Response.json({ status: "recorded", slot: body.slot, weird_level: body.weird_level }),
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
        if (url === STATUS_URL) {
            gateway.statusReads += 1;
            if (gateway.statusFailing || gateway.failedReads.has(gateway.statusReads)) {
                gateway.served.push("502");
                return new Response("Gateway worker restarted", { status: 502 });
            }
            gateway.served.push(gateway.status.stage);
            return Response.json({ ...gateway.status, status_poll_interval_seconds: gateway.pollSeconds });
        }
        if (url === "/api/story/new/weird" && init?.method === "PUT") {
            const body = JSON.parse(String(init.body));
            gateway.weirdSaves.push(body);
            return gateway.weirdAnswer(body);
        }
        if (url === "/api/story/new/transition") {
            gateway.transitionBodies.push(JSON.parse(String(init?.body)));
            return pending("transition", init?.signal);
        }
        if (url === "/api/narrative/continue") return pending("bootstrap", init?.signal);
        throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    return gateway;
}

function stage(name: string, detail: Record<string, unknown> = {}, run: string = THIS_RUN) {
    return { slot: 5, run, run_status: name === "failed" ? "failed" : name === "done" ? "done" : "running", error: name === "failed" ? "Stage failed" : null, stage: name, detail, updated_at: "2026-09-26T12:00:00+00:00", stages: [] };
}

// No run has started for the slot.
const NO_RUN = { slot: 5, run: null, run_status: null, error: null, stage: "idle", stages: [] };
const TRANSITIONED = { status: "transitioned", retrograde: { enabled: true } };

function renderReadyWizard(onComplete = vi.fn(), resumeData: WizardResumeData = readyWizard) {
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
                    resumeData={resumeData}
                    initialPhase={resumeData.current_phase === "ready" ? "seed" : resumeData.current_phase}
                />
                <Toaster />
            </ThemeProvider>
        </QueryClientProvider>,
    );
    return { ...view, onComplete };
}

async function confirmIntroduction() {
    await confirmIntroductionAvailable();
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
        // The read before the post names the run owning the record and the
        // poll interval; nothing is read from the operator plane.
        expect(gateway.requests.slice(0, 3)).toEqual([`GET ${STATUS_URL}`, `GET ${STATUS_URL}`, "POST /api/story/new/transition"]);
        await waitFor(() => expect(gateway.statusReads).toBeGreaterThan(1));
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
        expect(gateway.requests.filter((request) => request.includes("/api/settings"))).toEqual([]);
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

        // Retry starts a fresh run from an empty track. Its read before the
        // post finds the failure, now the previous run's record, and its
        // reads skip that record until the retry's run replaces it.
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        await waitFor(() => expect(pipStates()).toEqual(Array(6).fill("pending")));
        expect(screen.queryByText("Generation Failed")).toBeNull();
        await waitFor(() =>
            expect(gateway.requests.filter((request) => request === "POST /api/story/new/transition")).toHaveLength(2),
        );
        const readsBeforeRetryRun = gateway.statusReads;
        await waitFor(() => expect(gateway.statusReads).toBeGreaterThan(readsBeforeRetryRun + 2));
        expect(pipStates()).toEqual(Array(6).fill("pending"));
        gateway.status = stage("packet", {}, RETRY_RUN);
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
    });

    it("stops reading when the run reports failed while the response is still in flight", async () => {
        const gateway = stubGateway();
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.transition).not.toBeNull());
        // This run's first record the reads see is already terminal.
        gateway.status = stage("failed", { stage: "embedding" });
        await waitFor(() => expect(pipStates()).toEqual(track(4)));
        await expectNoFurtherStatusReads(gateway);
    });

    it.each([
        ["failed", { stage: "persistence" }],
        ["done", { embedded_summaries: 4 }],
    ])("reads past the previous run's %s record until this run reports", async (name, detail) => {
        const gateway = stubGateway();
        // The post's first reads can precede its run's replacement of the record.
        gateway.status = stage(name, detail, PREVIOUS_RUN);
        renderReadyWizard();
        await confirmIntroduction();
        await waitFor(() => expect(gateway.statusReads).toBeGreaterThan(3));
        expect(pipStates()).toEqual(Array(6).fill("pending"));

        gateway.status = stage("idle");
        await waitFor(() => expect(gateway.served.at(-1)).toBe("idle"));
        gateway.status = stage("packet");
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
    });

    it.each([
        ["no run", NO_RUN],
        ["the previous run's failure", stage("failed", { stage: "embedding" }, PREVIOUS_RUN)],
    ])(
        "marks the failed stage when this run's failure is the first record read after the post (before it: %s)",
        async (_before, before) => {
            const gateway = stubGateway();
            // No interval read comes before the transition answers.
            gateway.pollSeconds = 60;
            gateway.status = before;
            renderReadyWizard();
            await confirmIntroduction();
            await waitFor(() => expect(gateway.transition).not.toBeNull());
            expect(gateway.statusReads).toBe(2);

            gateway.status = stage("failed", { stage: "persistence" });
            vi.spyOn(console, "error").mockImplementation(() => {});
            await act(async () =>
                gateway.transition!.resolve(
                    Response.json({ detail: "Retrograde persistence blocked: 2 unresolved refs" }, { status: 400 }),
                ),
            );
            expect(await screen.findByText("Retrograde persistence blocked: 2 unresolved refs")).toBeInTheDocument();
            expect(pipStates()).toEqual(track(3, "failed"));
            expect(gateway.served).toEqual([before.stage, before.stage, "failed"]);
        },
    );

    it("marks the failed stage from the final read after the first stage read failed", async () => {
        const gateway = stubGateway();
        // The read before the post succeeds; the first interval read fails.
        gateway.failedReads.add(3);
        vi.spyOn(console, "error").mockImplementation(() => {});
        renderReadyWizard();
        await confirmIntroduction();
        expect(await screen.findByText("502: Gateway worker restarted")).toBeInTheDocument();
        await expectNoFurtherStatusReads(gateway);

        gateway.status = stage("failed", { stage: "embedding" });
        await act(async () =>
            gateway.transition!.resolve(
                Response.json({ detail: "Transition failed: embedding provider timeout" }, { status: 500 }),
            ),
        );
        expect(await screen.findByText("Transition failed: embedding provider timeout")).toBeInTheDocument();
        expect(pipStates()).toEqual(track(4, "failed"));
        expect(gateway.served).toEqual(["idle", "idle", "502", "failed"]);
    });

    it("marks no stage failed when the transition is refused before its run starts", async () => {
        const gateway = stubGateway();
        gateway.status = stage("failed", { stage: "persistence" }, PREVIOUS_RUN);
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
        gateway.statusFailing = true;
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
        // The first interval read, after the post, fails.
        gateway.failedReads.add(3);
        await confirmIntroduction();

        expect(await screen.findByText("502: Gateway worker restarted")).toBeInTheDocument();
        expect(screen.getByText("Transmission Error")).toBeInTheDocument();
        await expectNoFurtherStatusReads(gateway);

        await act(async () => gateway.transition!.resolve(Response.json(TRANSITIONED)));
        await waitFor(() => expect(gateway.bootstrap).not.toBeNull());
        await act(async () => gateway.bootstrap!.resolve(Response.json({ session_id: "opening-session" })));
        await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    });

    it("posts no transition when the read before it fails", async () => {
        const gateway = stubGateway();
        gateway.statusFailing = true;
        vi.spyOn(console, "error").mockImplementation(() => {});
        renderReadyWizard();
        await confirmIntroduction();
        expect(await screen.findByText("502: Gateway worker restarted")).toBeInTheDocument();
        expect(screen.getByText("Generation Failed")).toBeInTheDocument();
        await expectNoFurtherStatusReads(gateway);
        expect(gateway.statusReads).toBe(2);
        expect(gateway.transition).toBeNull();
    });

    it("reports a missing poll interval instead of guessing one", async () => {
        const gateway = stubGateway();
        gateway.pollSeconds = undefined;
        vi.spyOn(console, "error").mockImplementation(() => {});
        renderReadyWizard();
        await confirmIntroduction();
        expect(
            await screen.findByText(
                "nexus.toml [orrery.retrograde.wizard] status_poll_interval_seconds must be a positive number",
            ),
        ).toBeInTheDocument();
        expect(gateway.transition).toBeNull();
        expect(gateway.statusReads).toBe(2);
    });
});

describe("genesis reattach", () => {
    it("disables Confirm during the mount read and aborts it on unmount", async () => {
        let answer!: (response: Response) => void;
        let signal!: AbortSignal;
        const fetch = vi.fn((_url: string, init?: RequestInit) => {
            signal = init!.signal!;
            return new Promise<Response>(resolve => { answer = resolve; });
        });
        vi.stubGlobal("fetch", fetch);
        const { unmount, onComplete } = renderReadyWizard();
        expect(await screen.findByRole("button", { name: "Processing..." })).toBeDisabled();
        expect(fetch).toHaveBeenCalledTimes(1);
        unmount();
        expect(signal.aborted).toBe(true);
        await act(async () => answer(Response.json({
            ...stage("packet"), status_poll_interval_seconds: 0.01,
        })));
        expect(onComplete).not.toHaveBeenCalled();
        expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("stops the reattached running poll on unmount", async () => {
        const gateway = stubGateway();
        gateway.status = stage("packet");
        const { unmount } = renderReadyWizard();
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
        await waitFor(() => expect(gateway.statusReads).toBeGreaterThan(1));
        unmount();
        await expectNoFurtherStatusReads(gateway);
        expect(gateway.transitionBodies).toEqual([]);
        expect(gateway.bootstrap).toBeNull();
    });

    it("reattaches the wait screen to a running run on mount", async () => {
        const gateway = stubGateway();
        gateway.status = stage("expansion");
        const { onComplete } = renderReadyWizard();
        await waitFor(() => expect(pipStates()).toEqual(track(2)));
        expect(gateway.transitionBodies).toEqual([]);
        gateway.status = stage("done", { embedded_summaries: 2 });
        await waitFor(() => expect(gateway.bootstrap).not.toBeNull());
        expect(pipStates()).toEqual(track(5));
        await act(async () => gateway.bootstrap!.resolve(Response.json({ session_id: "reattached-opening" })));
        expect(onComplete).toHaveBeenCalledTimes(1);
        expect(JSON.parse(localStorage.getItem("pendingBootstrapSession")!)).toMatchObject({
            slot: 5, sessionId: "reattached-opening",
        });
        await expectNoFurtherStatusReads(gateway);
    });

    it("shows a reattached run's failure with Retry", async () => {
        const gateway = stubGateway();
        gateway.status = stage("packet");
        renderReadyWizard();
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
        gateway.status = { ...stage("failed", { stage: "packet" }), error: "Packet refused" };
        expect(await screen.findByText("Packet refused")).toBeInTheDocument();
        expect(pipStates()).toEqual(track(0, "failed"));
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        await waitFor(() => expect(gateway.transitionBodies).toEqual([{ slot: 5 }]));
    });

    it("shows a stage read error during reattach with Retry and Cancel", async () => {
        const gateway = stubGateway();
        gateway.status = stage("expansion");
        gateway.failedReads.add(2);
        renderReadyWizard();
        expect(await screen.findByText("502: Gateway worker restarted")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        await confirmIntroductionAvailable();
        expect(screen.queryAllByTestId("wait-stage")).toHaveLength(0);
        expect(gateway.transitionBodies).toEqual([]);
        await expectNoFurtherStatusReads(gateway);
    });

    it("waits through derivation with no pip lit", async () => {
        const gateway = stubGateway();
        gateway.status = stage("idle");
        renderReadyWizard();
        await waitFor(() => expect(pipStates()).toEqual(Array(6).fill("pending")));
        await waitFor(() => expect(gateway.statusReads).toBeGreaterThan(2));
        gateway.status = stage("packet");
        await waitFor(() => expect(pipStates()).toEqual(track(0)));
        expect(gateway.transitionBodies).toEqual([]);
    });

    it.each(["done", "failed"])("does not reattach to a %s run", async (name) => {
        const gateway = stubGateway();
        gateway.status = stage(name, name === "failed" ? { stage: "packet" } : {});
        renderReadyWizard();
        await confirmIntroductionAvailable();
        expect(screen.queryAllByTestId("wait-stage")).toHaveLength(0);
        expect(gateway.transitionBodies).toEqual([]);
        expect(gateway.bootstrap).toBeNull();
        expect(gateway.statusReads).toBe(1);
        await expectNoFurtherStatusReads(gateway);
    });

    it("keeps skipped pips dim when a reattached run finishes without Retrograde", async () => {
        const gateway = stubGateway();
        gateway.status = stage("idle");
        renderReadyWizard();
        await waitFor(() => expect(pipStates()).toEqual(Array(6).fill("pending")));
        gateway.status = { ...stage("idle"), run_status: "done" };
        await waitFor(() => expect(gateway.bootstrap).not.toBeNull());
        expect(pipStates()).toEqual([...Array(5).fill("skipped"), "active"]);
    });

    it("shows a reattached bootstrap failure and releases Confirm after Cancel", async () => {
        const gateway = stubGateway();
        gateway.status = stage("embedding");
        renderReadyWizard();
        await waitFor(() => expect(pipStates()).toEqual(track(4)));
        gateway.status = stage("done");
        await waitFor(() => expect(gateway.bootstrap).not.toBeNull());
        await act(async () => gateway.bootstrap!.resolve(Response.json({ detail: "Opening unavailable" }, { status: 503 })));
        expect(await screen.findByText("Opening unavailable")).toBeInTheDocument();
        expect(pipStates()).toEqual(track(5, "failed"));
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        await confirmIntroductionAvailable();
    });

    it("ends reattached polling on unmount and never completes an aborted bootstrap", async () => {
        const gateway = stubGateway();
        gateway.status = stage("embedding");
        const { unmount, onComplete } = renderReadyWizard();
        await waitFor(() => expect(pipStates()).toEqual(track(4)));
        gateway.status = stage("done");
        await waitFor(() => expect(gateway.bootstrap).not.toBeNull());
        unmount();
        await act(async () => gateway.bootstrap!.resolve(Response.json({ session_id: "late-opening" })));
        expect(onComplete).not.toHaveBeenCalled();
        expect(localStorage.getItem("pendingBootstrapSession")).toBeNull();
        await expectNoFurtherStatusReads(gateway);
    });

    it("shows a mount-read error and releases the artifact review", async () => {
        const gateway = stubGateway();
        gateway.statusFailing = true;
        renderReadyWizard();
        expect(await screen.findByText("502: Gateway worker restarted")).toBeInTheDocument();
        expect(screen.getByText("Transmission Error")).toBeInTheDocument();
        await confirmIntroductionAvailable();
        expect(screen.queryAllByTestId("wait-stage")).toHaveLength(0);
        expect(gateway.transitionBodies).toEqual([]);
    });
});

describe("genesis strangeness", () => {
    const glyph = (level: string) => screen.getByRole("button", { name: `Strangeness: ${level}` });
    const pressed = () =>
        ["low", "medium", "high"].filter((level) => glyph(level).getAttribute("aria-pressed") === "true");

    it("offers three distinctly shaped, unlabeled glyphs and presses only the saved level", async () => {
        stubGateway();
        renderReadyWizard(vi.fn(), { ...readyWizard, weird_level: "low" });
        await confirmIntroductionAvailable();

        expect(pressed()).toEqual(["low"]);
        const shapes = ["low", "medium", "high"].map((level) => {
            const button = glyph(level);
            // No visible text: the glyph and its accessible name carry it.
            expect(button).toHaveTextContent("");
            return button.querySelector("svg")?.getAttribute("class")?.match(/lucide-[a-z-]+/)?.[0];
        });
        expect(new Set(shapes).size).toBe(3);
        expect(document.body.textContent).not.toMatch(/strange|weird/i);
    });

    it("presses a glyph only after the gateway saves its level", async () => {
        const gateway = stubGateway();
        const echo = gateway.weirdAnswer;
        let answer!: (response: Response) => void;
        // Hold the first save in flight; later saves are echoed.
        gateway.weirdAnswer = () => {
            gateway.weirdAnswer = echo;
            return new Promise<Response>((resolve) => { answer = resolve; });
        };
        renderReadyWizard();
        await confirmIntroductionAvailable();
        expect(pressed()).toEqual([]);

        fireEvent.click(glyph("high"));
        await waitFor(() => expect(gateway.weirdSaves).toEqual([{ slot: 5, weird_level: "high" }]));
        expect(pressed()).toEqual([]);
        expect(glyph("medium")).toBeDisabled();

        await act(async () => answer(Response.json({ status: "recorded", slot: 5, weird_level: "high" })));
        await waitFor(() => expect(pressed()).toEqual(["high"]));
        expect(glyph("medium")).toBeEnabled();

        fireEvent.click(glyph("medium"));
        await waitFor(() => expect(pressed()).toEqual(["medium"]));
    });

    it("posts the level chosen after the introduction was offered with the transition", async () => {
        const gateway = stubGateway();
        renderReadyWizard(vi.fn(), { ...readyWizard, weird_level: "low" });
        await confirmIntroductionAvailable();

        fireEvent.click(glyph("high"));
        await waitFor(() => expect(pressed()).toEqual(["high"]));
        await confirmIntroduction();

        await waitFor(() => expect(gateway.transition).not.toBeNull());
        expect(gateway.transitionBodies).toEqual([{ slot: 5, weird_level: "high" }]);
    });

    it.each([
        ["low" as const, { slot: 5, weird_level: "low" }],
        // Nothing chosen: the server's stored selection or default applies.
        [null, { slot: 5 }],
    ])("posts the resumed level (%s) when the player keeps it", async (stored, body) => {
        const gateway = stubGateway();
        renderReadyWizard(vi.fn(), { ...readyWizard, weird_level: stored });
        await confirmIntroduction();

        await waitFor(() => expect(gateway.transition).not.toBeNull());
        expect(gateway.transitionBodies).toEqual([body]);
        expect(gateway.weirdSaves).toEqual([]);
    });

    it("keeps the saved level and reports a refused save", async () => {
        const gateway = stubGateway();
        gateway.weirdAnswer = () =>
            Response.json({ detail: "The wizard changed while this response was being generated." }, { status: 409 });
        vi.spyOn(console, "error").mockImplementation(() => {});
        renderReadyWizard(vi.fn(), { ...readyWizard, weird_level: "medium" });
        await confirmIntroductionAvailable();

        fireEvent.click(glyph("high"));
        expect(await screen.findByText("The wizard changed while this response was being generated.")).toBeInTheDocument();
        expect(pressed()).toEqual(["medium"]);
    });

    it("holds Confirm, label unchanged, while a strangeness save is in flight", async () => {
        const gateway = stubGateway();
        const answer = holdWeirdSave(gateway);
        renderReadyWizard(vi.fn(), { ...readyWizard, weird_level: "low" });
        await confirmIntroductionAvailable();
        const confirm = screen.getByRole("button", { name: "Confirm" });

        fireEvent.click(glyph("high"));
        await waitFor(() => expect(confirm).toBeDisabled());
        expect(confirm).toHaveTextContent("Confirm");
        fireEvent.click(confirm);

        await act(async () => answer(Response.json({ status: "recorded", slot: 5, weird_level: "high" })));
        await waitFor(() => expect(pressed()).toEqual(["high"]));
        expect(confirm).toBeEnabled();
        // The click on the held Confirm started nothing.
        expect(gateway.statusReads).toBe(1);
        expect(gateway.transitionBodies).toEqual([]);

        fireEvent.click(confirm);
        await waitFor(() => expect(gateway.transition).not.toBeNull());
        expect(gateway.transitionBodies).toEqual([{ slot: 5, weird_level: "high" }]);
    });

    it("posts a level still being saved at Confirm only once the gateway has saved it", async () => {
        const gateway = stubGateway();
        const answer = holdWeirdSave(gateway);
        renderReadyWizard(vi.fn(), { ...readyWizard, weird_level: "low" });
        await confirmIntroductionAvailable();

        // Confirm lands in the glyph's frame, before the held save disables it.
        act(() => {
            fireEvent.click(glyph("high"));
            fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
        });
        await waitFor(() => expect(gateway.weirdSaves).toEqual([{ slot: 5, weird_level: "high" }]));
        await settle();
        expect(gateway.transitionBodies).toEqual([]);

        await act(async () => answer(Response.json({ status: "recorded", slot: 5, weird_level: "high" })));
        await waitFor(() => expect(gateway.transition).not.toBeNull());
        expect(gateway.transitionBodies).toEqual([{ slot: 5, weird_level: "high" }]);
        expect(gateway.requests).toEqual([`GET ${STATUS_URL}`,
            "PUT /api/story/new/weird",
            SAVE_ANSWERED,
            `GET ${STATUS_URL}`,
            "POST /api/story/new/transition",
            ...gateway.requests.slice(5),
        ]);
    });

    it("starts no transition when a save in flight at Confirm is refused", async () => {
        const gateway = stubGateway();
        const answer = holdWeirdSave(gateway);
        vi.spyOn(console, "error").mockImplementation(() => {});
        renderReadyWizard(vi.fn(), { ...readyWizard, weird_level: "medium" });
        await confirmIntroductionAvailable();

        act(() => {
            fireEvent.click(glyph("high"));
            fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
        });
        await waitFor(() => expect(gateway.weirdSaves).toEqual([{ slot: 5, weird_level: "high" }]));
        await act(async () =>
            answer(Response.json({ detail: "The wizard changed while this response was being generated." }, { status: 409 })),
        );

        expect(await screen.findByText("The wizard changed while this response was being generated.")).toBeInTheDocument();
        await settle();
        expect(gateway.requests).toEqual([`GET ${STATUS_URL}`, "PUT /api/story/new/weird", SAVE_ANSWERED]);
        expect(gateway.transitionBodies).toEqual([]);
        expect(screen.queryAllByTestId("wait-stage")).toHaveLength(0);
        expect(pressed()).toEqual(["medium"]);
        // The Introduction can be confirmed again, with the level it shows.
        await confirmIntroductionAvailable();
    });

    it("appears only on the Introduction", async () => {
        stubGateway();
        renderReadyWizard(vi.fn(), {
            ...readyWizard,
            current_phase: "setting",
            selected_seed: null,
            layer_draft: null,
            zone_draft: null,
            initial_location: null,
        });
        expect(await screen.findByText("Your story is ready to begin.")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /Strangeness/ })).toBeNull();
    });
});

/** The ready wizard has restored its introduction and offers Confirm. */
async function confirmIntroductionAvailable() {
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled());
}

// Logged among the gateway's requests when a held strangeness save is answered.
const SAVE_ANSWERED = "answered PUT /api/story/new/weird";

/** Holds the next strangeness save in flight until the returned answer settles it. */
function holdWeirdSave(gateway: ReturnType<typeof stubGateway>) {
    let settle!: (response: Response) => void;
    gateway.weirdAnswer = () => new Promise<Response>((resolve) => { settle = resolve; });
    return (response: Response) => {
        gateway.requests.push(SAVE_ANSWERED);
        settle(response);
    };
}

/** Lets anything the wizard would start next reach the gateway. */
async function settle() {
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
}
