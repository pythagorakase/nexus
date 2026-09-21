import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InteractiveWizard } from "./InteractiveWizard";

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
        render(<InteractiveWizard {...props} />);

        expect(await screen.findByRole("alert")).toHaveTextContent("Conversation service unavailable");
        expect(screen.getByRole("button", { name: "Accept Fate" })).toBeDisabled();
        expect(screen.queryByTestId("wizard-freeform")).toBeNull();

        fireEvent.click(screen.getByRole("button", { name: "Retry" }));

        expect(await screen.findByText("Where does your story begin?")).toBeInTheDocument();
        expect(screen.getByTestId("wizard-choice-1")).toBeEnabled();
        expect(screen.getByTestId("wizard-freeform")).toBeEnabled();
        expect(screen.queryByRole("alert")).toBeNull();
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
        expect(fetch).toHaveBeenCalledTimes(2);
        expect(screen.queryByText("Wrong slot")).toBeNull();
    });
});
