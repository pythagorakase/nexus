import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { WaitScreen } from "./WaitScreen";

const STAGES = ["packet", "seed_candidates", "expansion", "persistence", "embedding", "bootstrap"] as const;
type Stage = (typeof STAGES)[number];

function renderWaitScreen(
    currentStage: Stage | null,
    options: {
        skippedStages?: readonly Stage[];
        hasError?: boolean;
        errorMessage?: string;
        onRetry?: () => void;
        onCancel?: () => void;
    } = {},
) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    queryClient.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
    queryClient.setQueryData(["/api/preferences"], { theme: "veil" });
    return render(
        <QueryClientProvider client={queryClient}>
            <ThemeProvider>
                <WaitScreen
                    statusText="Initializing your world..."
                    elapsedSeconds={125}
                    stages={STAGES}
                    currentStage={currentStage}
                    skippedStages={options.skippedStages}
                    onRetry={options.onRetry ?? (() => {})}
                    onCancel={options.onCancel ?? (() => {})}
                    hasError={options.hasError}
                    errorMessage={options.errorMessage}
                />
            </ThemeProvider>
        </QueryClientProvider>,
    );
}

const pipStates = () => screen.getAllByTestId("wait-stage").map((pip) => pip.getAttribute("data-state"));

describe("WaitScreen stage track", () => {
    it("shows every stage pending before the first stage reports", () => {
        renderWaitScreen(null);
        expect(pipStates()).toEqual(Array(6).fill("pending"));
        expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    });

    it.each(STAGES.map((stage, index) => [stage, index] as const))(
        "lights completed stages and glows the active %s stage",
        (stage, index) => {
            renderWaitScreen(stage);
            expect(pipStates()).toEqual(
                STAGES.map((_, i) => (i < index ? "done" : i === index ? "active" : "pending")),
            );
            const progress = screen.getByRole("progressbar");
            expect(progress).toHaveAttribute("aria-valuenow", String(index));
            expect(progress).toHaveAttribute("aria-valuemax", "6");
        },
    );

    it("renders no percentage, no stage captions, and a truthful MM:SS timer", () => {
        const { container } = renderWaitScreen("expansion");
        expect(screen.getByText("02:05")).toBeInTheDocument();
        expect(container.textContent).not.toMatch(/%/);
        for (const stage of STAGES) {
            expect(container.textContent).not.toContain(stage);
        }
        for (const pip of screen.getAllByTestId("wait-stage")) {
            expect(pip).toBeEmptyDOMElement();
        }
    });

    it("marks the failed stage in the danger colour and keeps the error, Retry and Cancel", () => {
        const onRetry = vi.fn();
        const onCancel = vi.fn();
        renderWaitScreen("persistence", {
            hasError: true,
            errorMessage: "Retrograde persistence is blocked",
            onRetry,
            onCancel,
        });
        expect(pipStates()).toEqual(["done", "done", "done", "failed", "pending", "pending"]);
        expect(screen.getAllByTestId("wait-stage")[3]).toHaveClass("bg-destructive");
        expect(screen.getByRole("heading")).toHaveTextContent("Generation Failed");
        expect(screen.getByText("Retrograde persistence is blocked")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(onRetry).toHaveBeenCalledTimes(1);
        expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it("keeps skipped stages dim once the operation passes them", () => {
        renderWaitScreen("bootstrap", { skippedStages: STAGES.slice(0, 5) });
        expect(pipStates()).toEqual([...Array(5).fill("skipped"), "active"]);
        for (const pip of screen.getAllByTestId("wait-stage").slice(0, 5)) {
            expect(pip).toHaveClass("bg-muted");
        }
        const progress = screen.getByRole("progressbar");
        expect(progress).toHaveAttribute("aria-valuenow", "0");
        expect(progress).toHaveAttribute("aria-valuemax", "1");
    });

    it("keeps every pip dim when a failure precedes the first stage", () => {
        renderWaitScreen(null, { hasError: true, errorMessage: "Setup data validation failed" });
        expect(pipStates()).toEqual(Array(6).fill("pending"));
        expect(screen.getByText("Setup data validation failed")).toBeInTheDocument();
    });

    it("rejects a current stage outside the stage list", () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        expect(() => renderWaitScreen("weaving" as Stage)).toThrow(
            "Wait stage weaving is not one of packet, seed_candidates, expansion, persistence, embedding, bootstrap",
        );
    });
});
