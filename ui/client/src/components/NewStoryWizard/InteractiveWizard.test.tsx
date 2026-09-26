import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InteractiveWizard, type WizardResumeData } from "./InteractiveWizard";

vi.mock("./ArtifactSidePanel", () => ({ ArtifactSidePanel: () => null }));
vi.mock("@/components/ai", () => ({
    Conversation: ({ children }: any) => <div>{children}</div>,
    ConversationContent: ({ children }: any) => <div>{children}</div>,
    ConversationScrollButton: () => null,
    Loader: () => <span role="status">Loading</span>,
    Response: ({ children }: any) => <div>{children}</div>,
}));

const props = {
    slot: 5,
    onComplete: vi.fn(),
    onCancel: vi.fn(),
    onPhaseChange: vi.fn(),
    wizardData: {},
    setWizardData: vi.fn(),
};

afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe("wizard initialization", () => {
    it("keeps the server error visible and retries into usable choices", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        const fetch = vi.fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Conversation service unavailable" }), { status: 503 }))
            .mockResolvedValueOnce(new Response(JSON.stringify({
                thread_id: "conv_new",
                welcome_message: "Where does your story begin?",
                welcome_choices: ["A moonlit harbor"],
            })));
        vi.stubGlobal("fetch", fetch);
        localStorage.setItem("activeSlot", "2");
        render(<InteractiveWizard {...props} />);

        expect(await screen.findByRole("alert")).toHaveTextContent("Conversation service unavailable");
        expect(screen.getByRole("button", { name: "Accept Fate" })).toBeDisabled();
        expect(screen.queryByTestId("wizard-freeform")).toBeNull();

        expect(localStorage.getItem("activeSlot")).toBe("2");
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));

        expect(await screen.findByText("Where does your story begin?")).toBeInTheDocument();
        expect(screen.getByTestId("wizard-choice-1")).toBeEnabled();
        expect(screen.getByTestId("wizard-freeform")).toBeEnabled();
        expect(screen.queryByRole("alert")).toBeNull();
        expect(localStorage.getItem("activeSlot")).toBe("5");
        expect(fetch).toHaveBeenCalledTimes(2);
        expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ slot: 5 });
    });

    it("shows an actionable error when the server returns a non-JSON failure", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad Gateway", { status: 502 })));
        render(<InteractiveWizard {...props} />);
        expect(await screen.findByRole("alert")).toHaveTextContent("Could not start a new story (502).");
        expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
    });

    it("ignores a late initialization response from a previous slot", async () => {
        let finishFirst!: (response: Response) => void;
        const fetch = vi.fn()
            .mockReturnValueOnce(new Promise<Response>(resolve => { finishFirst = resolve; }))
            .mockResolvedValueOnce(new Response(JSON.stringify({ thread_id: "conv_current", welcome_message: "Current slot" })));
        vi.stubGlobal("fetch", fetch);
        const { rerender } = render(<InteractiveWizard {...props} slot={4} />);
        rerender(<InteractiveWizard {...props} slot={5} />);
        expect(await screen.findByText("Current slot")).toBeInTheDocument();
        await act(async () => {
            finishFirst(new Response(JSON.stringify({ thread_id: "conv_old", welcome_message: "Wrong slot" })));
        });
        expect(localStorage.getItem("activeSlot")).toBe("5");
        expect(fetch).toHaveBeenCalledTimes(2);
        expect(screen.queryByText("Wrong slot")).toBeNull();
    });
});

const resumeData: WizardResumeData = {
    thread_id: "conv_saved",
    current_phase: "setting",
    messages: [{ role: "assistant", content: "Where shall we begin?" }],
    choices: ["A moonlit harbor"],
    setting_draft: null,
    character_draft: null,
    character_state: null,
    selected_seed: null,
    layer_draft: null,
    zone_draft: null,
    initial_location: null,
};

describe("wizard composer recovery", () => {
    it("restores exact unsent input on resume but isolates a new wizard in the same slot", async () => {
        const fetch = vi.fn();
        vi.stubGlobal("fetch", fetch);
        const draft = "  Begin at the harbor.\n\nLeave the door unlocked.  ";
        const first = render(<InteractiveWizard {...props} resumeData={resumeData} />);
        fireEvent.change(await screen.findByTestId("wizard-freeform"), { target: { value: draft } });
        first.unmount();
        const resumed = render(<InteractiveWizard {...props} resumeData={resumeData} />);
        expect(await screen.findByTestId("wizard-freeform")).toHaveValue(draft);
        expect(fetch).not.toHaveBeenCalled();
        resumed.unmount();
        render(<InteractiveWizard {...props} resumeData={{ ...resumeData, thread_id: "conv_replacement" }} />);
        expect(await screen.findByTestId("wizard-freeform")).toHaveValue("");
        expect(fetch).not.toHaveBeenCalled();
    });

    it.each([503, 200])("retains the draft after an unsuccessful or empty response (%s)", async (status) => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({}), { status }));
        vi.stubGlobal("fetch", fetch);
        const first = render(<InteractiveWizard {...props} resumeData={resumeData} />);
        const input = await screen.findByTestId("wizard-freeform");
        fireEvent.change(input, { target: { value: "  Keep the whole draft.\nEven this line.  " } });
        fireEvent.keyDown(input, { key: "Enter" });
        expect(await screen.findByTestId("wizard-freeform")).toHaveValue("  Keep the whole draft.\nEven this line.  ");
        expect(await screen.findByText(/Submission not confirmed/)).toBeInTheDocument();
        expect(fetch).toHaveBeenCalledTimes(1);
        first.unmount();
        render(<InteractiveWizard {...props} resumeData={resumeData} />);
        expect(await screen.findByTestId("wizard-freeform")).toHaveValue("  Keep the whole draft.\nEven this line.  ");
        expect(fetch).toHaveBeenCalledTimes(1);
    });

    it("clears acknowledged input after the loading screen remounts the composer", async () => {
        let finish!: (response: Response) => void;
        const fetch = vi.fn().mockReturnValue(new Promise<Response>(resolve => { finish = resolve; }));
        vi.stubGlobal("fetch", fetch);
        const first = render(<InteractiveWizard {...props} resumeData={resumeData} />);
        const input = await screen.findByTestId("wizard-freeform");
        fireEvent.change(input, { target: { value: "  A different harbor.  " } });
        fireEvent.keyDown(input, { key: "Enter" });
        expect(screen.queryByTestId("wizard-freeform")).toBeNull();
        await act(async () => {
            finish(new Response(JSON.stringify({ message: "Tell me about its people.", choices: ["Quiet smugglers"] })));
        });
        await waitFor(() => expect(screen.getByTestId("wizard-freeform")).toHaveValue(""));
        expect(screen.queryByText(/Submission not confirmed/)).toBeNull();
        expect(JSON.parse(fetch.mock.calls[0][1].body).message).toBe("A different harbor.");
        first.unmount();
        render(<InteractiveWizard {...props} resumeData={resumeData} />);
        expect(await screen.findByTestId("wizard-freeform")).toHaveValue("");
        expect(fetch).toHaveBeenCalledTimes(1);
    });
});
