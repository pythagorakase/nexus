import { TraitSelector } from "nexus-ui";

// The standalone trait picker: ten traits in four labeled categories, a row of
// indicator lights tracking the count, and a Confirm button. Pick exactly three.
// onConfirm / onInvalidConfirm are inert in preview.

// Complete selection: three traits chosen, lights turn emerald, Confirm goes
// active (green).
export const Complete = () => (
  <div style={{ width: 320, display: "flex", justifyContent: "center" }}>
    <TraitSelector
      suggestedTraits={["allies", "reputation", "enemies"]}
      onConfirm={() => {}}
      onInvalidConfirm={() => {}}
    />
  </div>
);

// Partial selection: two traits chosen — lights show primary (not yet complete),
// Confirm stays muted, and the "discuss with Skald" helper line appears.
export const Partial = () => (
  <div style={{ width: 320, display: "flex", justifyContent: "center" }}>
    <TraitSelector
      suggestedTraits={["patron", "domain"]}
      onConfirm={() => {}}
      onInvalidConfirm={() => {}}
    />
  </div>
);
