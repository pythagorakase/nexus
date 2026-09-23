import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewStoryWizard } from "./WizardShell";

vi.mock("./SlotSelector", () => ({
    SlotSelector: ({ onSlotResumed }: any) => (
        <button onClick={() => onSlotResumed({
            slot: 5, wizard_in_progress: true, wizard_thread_id: "conv_saved", wizard_phase: "setting",
        })}>Resume saved wizard</button>
    ),
}));
vi.mock("@/contexts/ThemeContext", () => ({ useTheme: () => ({}) }));
vi.mock("@/components/ThemeMenu", () => ({ ThemeMenu: () => null }));
vi.mock("@/components/ai", () => ({
    Conversation: ({ children }: any) => <div>{children}</div>,
    ConversationContent: ({ children }: any) => <div>{children}</div>,
    ConversationScrollButton: () => null,
    Loader: () => <span role="status">Loading</span>,
    Response: ({ children }: any) => <div>{children}</div>,
}));

const savedSession = {
    thread_id: "conv_saved",
    current_phase: "character",
    messages: [
        { role: "assistant", content: "Where does your story begin?" },
        { role: "user", content: "A forest full of old promises." },
        { role: "assistant", content: "Who lives in this forest?" },
    ],
    choices: ["A wanderer", "A keeper"],
    setting_draft: { world_name: "The Waking Wood" },
    character_draft: null,
    character_state: null,
    layer_draft: null,
    zone_draft: null,
    selected_seed: null,
    initial_location: null,
};

afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe("resuming a saved wizard", () => {
    it("renders the transcript and choices, then continues the same session with its drafts", async () => {
        const fetch = vi.fn()
            .mockResolvedValueOnce(new Response(JSON.stringify(savedSession)))
            .mockResolvedValueOnce(new Response(JSON.stringify({ message: "What does the wanderer seek?", choices: [] })));
        vi.stubGlobal("fetch", fetch);
        const { container } = render(<NewStoryWizard />);

        fireEvent.click(screen.getByRole("button", { name: "Resume saved wizard" }));

        expect(await screen.findByText("Who lives in this forest?")).toBeInTheDocument();
        expect(container.textContent).toMatch(/Where does your story begin\?[\s\S]*A forest full of old promises\.[\s\S]*Who lives in this forest\?/);
        expect(screen.getAllByText("Character", { exact: true }).length).toBeGreaterThan(0);
        expect(screen.getByTestId("wizard-choice-1")).toHaveTextContent("A wanderer");
        expect(screen.getByTestId("wizard-choice-2")).toHaveTextContent("A keeper");
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(fetch).toHaveBeenCalledWith("/api/story/new/setup/resume?slot=5", { signal: expect.any(AbortSignal) });
        expect(localStorage.getItem("activeSlot")).toBe("5");

        fireEvent.click(screen.getByTestId("wizard-choice-1"));
        expect(await screen.findByText("What does the wanderer seek?")).toBeInTheDocument();
        expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({
            slot: 5,
            thread_id: "conv_saved",
            current_phase: "character",
            message: "A wanderer",
            context_data: { setting: savedSession.setting_draft },
        });
        expect(screen.queryByTestId("wizard-choice-1")).toBeNull();
    });

    it("keeps the saved slot available for retry when history cannot be loaded", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        const fetch = vi.fn()
            .mockResolvedValueOnce(new Response("Service unavailable", { status: 503 }))
            .mockResolvedValueOnce(new Response(JSON.stringify(savedSession)));
        vi.stubGlobal("fetch", fetch);
        localStorage.setItem("activeSlot", "2");
        render(<NewStoryWizard />);

        fireEvent.click(screen.getByRole("button", { name: "Resume saved wizard" }));
        await vi.waitFor(() => expect(console.error).toHaveBeenCalled());
        expect(screen.queryByTestId("wizard-freeform")).toBeNull();
        expect(localStorage.getItem("activeSlot")).toBe("2");
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        expect(await screen.findByText("Who lives in this forest?")).toBeInTheDocument();
        expect(fetch.mock.calls.every(([url]) => url === "/api/story/new/setup/resume?slot=5")).toBe(true);
    });
});


describe("automatic wizard resume", () => {
    const characterState = {
        concept: {
            name: "Rowan", archetype: "Keeper",
            suggested_traits: ["bond", "duty", "secret"],
            trait_rationales: { bond: "An old promise", duty: "The gate", secret: "A hidden name" },
        },
    };

    it("restores trait selection and sends the saved concept when confirming", async () => {
        const fetch = vi.fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({ ...savedSession, choices: [], character_state: characterState })))
            .mockResolvedValueOnce(new Response(JSON.stringify({ message: "Describe your wildcard", choices: [] })));
        vi.stubGlobal("fetch", fetch);
        render(<NewStoryWizard resumeSlot={5} />);

        expect(await screen.findByText("3 traits selected")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "bond" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
        expect(fetch).toHaveBeenCalledTimes(1);
        fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
        expect(await screen.findByText("Describe your wildcard")).toBeInTheDocument();
        expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({
            slot: 5, thread_id: "conv_saved", current_phase: "character",
            context_data: { character_state: characterState },
            message: "I'll take: bond, duty, secret",
        });
    });

    it("keeps confirmed traits in context while resuming the wildcard subphase", async () => {
        const state = { ...characterState, trait_selection: { selected_traits: ["bond", "duty", "secret"] } };
        const fetch = vi.fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({ ...savedSession, character_state: state })))
            .mockResolvedValueOnce(new Response(JSON.stringify({ message: "Tell me more", choices: [] })));
        vi.stubGlobal("fetch", fetch);
        render(<NewStoryWizard resumeSlot={5} />);
        fireEvent.click(await screen.findByTestId("wizard-choice-1"));
        expect(await screen.findByText("Tell me more")).toBeInTheDocument();
        expect(JSON.parse(fetch.mock.calls[1][1].body).context_data.character_state).toEqual(state);
        expect(screen.queryByText("Select Traits")).toBeNull();
    });

    it("restores the ready seed as a pending artifact and waits for Confirm to transition", async () => {
        const fetch = vi.fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({
                ...savedSession, current_phase: "ready", choices: [],
                character_draft: characterState,
                selected_seed: { title: "The missing key", hook: "The gate is open" },
                layer_draft: { name: "Mortal world" }, zone_draft: { name: "The wood" },
                initial_location: { name: "The gate", summary: "An ancient arch" },
            })))
            .mockReturnValueOnce(new Promise(() => {}));
        vi.stubGlobal("fetch", fetch);
        render(<NewStoryWizard resumeSlot={5} />);

        expect(await screen.findByText("The missing key")).toBeInTheDocument();
        expect(screen.getByText("An ancient arch")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
        expect(fetch).toHaveBeenCalledTimes(1);
        fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
        expect(fetch).toHaveBeenCalledTimes(2);
        expect(fetch.mock.calls[1][0]).toBe("/api/story/new/transition");
        expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ slot: 5 });
    });

    it("ignores a resume response after leaving the wizard", async () => {
        let finish!: (response: Response) => void;
        vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise<Response>(resolve => { finish = resolve; })));
        localStorage.setItem("activeSlot", "2");
        const { unmount } = render(<NewStoryWizard resumeSlot={5} />);
        unmount();
        await act(async () => finish(new Response(JSON.stringify(savedSession))));
        expect(localStorage.getItem("activeSlot")).toBe("2");
    });
});
