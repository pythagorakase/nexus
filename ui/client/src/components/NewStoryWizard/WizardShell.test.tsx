import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewStoryWizard } from "./WizardShell";

vi.mock("./SlotSelector", () => ({
    SlotSelector: ({ onSlotResumed }: any) => (
        <button onClick={() => onSlotResumed({
            slot: 5, wizard_in_progress: true, wizard_thread_id: "conv_saved", wizard_phase: "setting",
        })}>Resume saved wizard</button>
    ),
}));
vi.mock("./ArtifactSidePanel", () => ({ ArtifactSidePanel: () => null }));
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
    selected_seed: null,
    initial_location: null,
};

afterEach(() => {
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
        expect(screen.getByText("Character", { exact: true })).toBeInTheDocument();
        expect(screen.getByTestId("wizard-choice-1")).toHaveTextContent("A wanderer");
        expect(screen.getByTestId("wizard-choice-2")).toHaveTextContent("A keeper");
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(fetch).toHaveBeenCalledWith("/api/story/new/setup/resume?slot=5");

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
        render(<NewStoryWizard />);

        fireEvent.click(screen.getByRole("button", { name: "Resume saved wizard" }));
        await vi.waitFor(() => expect(console.error).toHaveBeenCalled());
        expect(screen.queryByTestId("wizard-freeform")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Resume saved wizard" }));
        expect(await screen.findByText("Who lives in this forest?")).toBeInTheDocument();
        expect(fetch.mock.calls.every(([url]) => url === "/api/story/new/setup/resume?slot=5")).toBe(true);
    });
});
