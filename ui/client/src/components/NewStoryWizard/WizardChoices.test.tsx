/**
 * Tests for the wizard's structured-choices + freeform composition:
 * normalization of backend turn payloads and the click/type/keyboard
 * interaction surface that replaced the wizard command bar.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { normalizeChoices, WizardChoices } from "./WizardChoices";

describe("normalizeChoices", () => {
    it("passes through string arrays, trimmed and filtered", () => {
        expect(normalizeChoices(["  A cyberpunk city ", "", "High fantasy"])).toEqual([
            "A cyberpunk city",
            "High fantasy",
        ]);
    });

    it("flattens structured {label, description} objects", () => {
        expect(
            normalizeChoices([{ label: "Noir", description: "Rain and neon" }]),
        ).toEqual(["Noir: Rain and neon"]);
    });

    it("returns an empty list for null, undefined, and non-arrays", () => {
        expect(normalizeChoices(null)).toEqual([]);
        expect(normalizeChoices(undefined)).toEqual([]);
        expect(normalizeChoices("not-an-array")).toEqual([]);
    });

    it("coerces unexpected member types to strings", () => {
        expect(normalizeChoices([42, " yes "])).toEqual(["42", "yes"]);
    });
});

describe("WizardChoices", () => {
    const choices = ["Build a floating city", "Start in the underdark"];

    it("renders one numbered button per choice", () => {
        render(<WizardChoices choices={choices} onSubmit={() => {}} />);
        expect(screen.getByTestId("wizard-choice-1")).toHaveTextContent(
            "Build a floating city",
        );
        expect(screen.getByTestId("wizard-choice-2")).toHaveTextContent(
            "Start in the underdark",
        );
    });

    it("submits the choice text on click", () => {
        const onSubmit = vi.fn();
        render(<WizardChoices choices={choices} onSubmit={onSubmit} />);
        fireEvent.click(screen.getByTestId("wizard-choice-2"));
        expect(onSubmit).toHaveBeenCalledWith("Start in the underdark");
    });

    it("always renders the freeform slot, even with no choices", () => {
        render(<WizardChoices choices={[]} onSubmit={() => {}} />);
        expect(screen.queryByRole("button")).toBeNull();
        expect(screen.getByTestId("wizard-freeform")).toBeInTheDocument();
    });

    it("submits trimmed freeform text on Enter and clears the field", () => {
        const onSubmit = vi.fn();
        render(<WizardChoices choices={choices} onSubmit={onSubmit} />);
        const freeform = screen.getByTestId("wizard-freeform");
        fireEvent.change(freeform, { target: { value: "  a haunted lighthouse  " } });
        fireEvent.keyDown(freeform, { key: "Enter" });
        expect(onSubmit).toHaveBeenCalledWith("a haunted lighthouse");
        expect(freeform).toHaveValue("");
    });

    it("does not submit empty freeform text", () => {
        const onSubmit = vi.fn();
        render(<WizardChoices choices={choices} onSubmit={onSubmit} />);
        const freeform = screen.getByTestId("wizard-freeform");
        fireEvent.change(freeform, { target: { value: "   " } });
        fireEvent.keyDown(freeform, { key: "Enter" });
        expect(onSubmit).not.toHaveBeenCalled();
    });

    it("inserts a newline instead of submitting on Shift+Enter", () => {
        const onSubmit = vi.fn();
        render(<WizardChoices choices={choices} onSubmit={onSubmit} />);
        const freeform = screen.getByTestId("wizard-freeform");
        fireEvent.change(freeform, { target: { value: "line one" } });
        fireEvent.keyDown(freeform, { key: "Enter", shiftKey: true });
        expect(onSubmit).not.toHaveBeenCalled();
    });

    it("selects a choice via number key when focus is outside the field", () => {
        const onSubmit = vi.fn();
        render(<WizardChoices choices={choices} onSubmit={onSubmit} />);
        fireEvent.keyDown(window, { key: "1" });
        expect(onSubmit).toHaveBeenCalledWith("Build a floating city");
    });

    it("ignores number keys typed inside the freeform field", () => {
        const onSubmit = vi.fn();
        render(<WizardChoices choices={choices} onSubmit={onSubmit} />);
        const freeform = screen.getByTestId("wizard-freeform");
        freeform.focus();
        fireEvent.keyDown(freeform, { key: "1" });
        expect(onSubmit).not.toHaveBeenCalled();
    });

    it("disables all interaction when disabled", () => {
        const onSubmit = vi.fn();
        render(<WizardChoices choices={choices} onSubmit={onSubmit} disabled />);
        fireEvent.keyDown(window, { key: "1" });
        expect(onSubmit).not.toHaveBeenCalled();
        expect(screen.getByTestId("wizard-choice-1")).toBeDisabled();
        expect(screen.getByTestId("wizard-freeform")).toBeDisabled();
    });
});
