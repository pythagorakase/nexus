import { WizardChoices } from "nexus-ui";

// The wizard's turn-input surface: numbered structured choices plus an
// always-present freeform "…or something else" slot. Mirrors the narrative
// reader's interaction pattern. onSubmit is inert in preview.
export const Choices = () => (
  <div style={{ width: 620 }}>
    <WizardChoices
      choices={[
        "A drowned harbor city where the tides obey no moon.",
        "A frontier mining colony clinging to a fractured asteroid.",
        "A walled archive-city where memory itself is currency.",
      ]}
      onSubmit={() => {}}
    />
  </div>
);

// The disabled state, shown while a turn is in flight or an artifact awaits
// confirmation — every choice and the freeform field dim and stop responding.
export const Disabled = () => (
  <div style={{ width: 620 }}>
    <WizardChoices
      choices={[
        "Press the Tidewardens for safe passage across the flood district.",
        "Slip into the customs house alone and search for the vault ledger.",
      ]}
      disabled
      onSubmit={() => {}}
    />
  </div>
);
