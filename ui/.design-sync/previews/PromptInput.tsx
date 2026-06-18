import {
  PromptInput,
  PromptInputTextarea,
  PromptInputToolbar,
  PromptInputTools,
  PromptInputModelSelect,
  PromptInputModelSelectTrigger,
  PromptInputModelSelectContent,
  PromptInputModelSelectItem,
  PromptInputModelSelectValue,
  PromptInputSubmit,
} from "nexus-ui";

// The resting composer: prompt textarea, an inline model picker, and the send
// button. This is what the player types each turn into.
export const Ready = () => (
  <div style={{ width: 600 }}>
    <PromptInput>
      <PromptInputTextarea
        defaultValue="I ask the Archivist to unseal the lower vault — and offer the clerk's phrase as proof."
        placeholder="What do you do?"
      />
      <PromptInputToolbar>
        <PromptInputTools>
          <PromptInputModelSelect defaultValue="frontier">
            <PromptInputModelSelectTrigger>
              <PromptInputModelSelectValue placeholder="Choose a Model" />
            </PromptInputModelSelectTrigger>
            <PromptInputModelSelectContent>
              <PromptInputModelSelectItem value="frontier">
                Frontier Author
              </PromptInputModelSelectItem>
              <PromptInputModelSelectItem value="balanced">
                Balanced Narrator
              </PromptInputModelSelectItem>
            </PromptInputModelSelectContent>
          </PromptInputModelSelect>
        </PromptInputTools>
        <PromptInputSubmit status="ready" />
      </PromptInputToolbar>
    </PromptInput>
  </div>
);

// The submit-button status axis: each chat phase swaps the trailing icon
// (send / spinner / stop square / error ✕).
export const SubmitStates = () => (
  <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
    <PromptInputSubmit status="ready" />
    <PromptInputSubmit status="submitted" />
    <PromptInputSubmit status="streaming" />
    <PromptInputSubmit status="error" />
  </div>
);

// The composer with its model picker rendered open, showing the portalled
// option list landing in-frame (extra bottom padding reserves the space).
export const ModelPicker = () => (
  <div style={{ width: 600, paddingBottom: 200 }}>
    <PromptInput>
      <PromptInputTextarea
        defaultValue="Cross the flood district to reach the Spire before dawn."
        placeholder="What do you do?"
      />
      <PromptInputToolbar>
        <PromptInputTools>
          <PromptInputModelSelect defaultValue="frontier" open>
            <PromptInputModelSelectTrigger>
              <PromptInputModelSelectValue placeholder="Choose a Model" />
            </PromptInputModelSelectTrigger>
            <PromptInputModelSelectContent position="item-aligned">
              <PromptInputModelSelectItem value="frontier">
                Frontier Author
              </PromptInputModelSelectItem>
              <PromptInputModelSelectItem value="balanced">
                Balanced Narrator
              </PromptInputModelSelectItem>
              <PromptInputModelSelectItem value="economy">
                Economy Draft
              </PromptInputModelSelectItem>
            </PromptInputModelSelectContent>
          </PromptInputModelSelect>
        </PromptInputTools>
        <PromptInputSubmit status="ready" />
      </PromptInputToolbar>
    </PromptInput>
  </div>
);
