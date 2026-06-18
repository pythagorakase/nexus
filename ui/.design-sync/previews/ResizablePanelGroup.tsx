import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "nexus-ui";

// Horizontal split: narrative pane beside a ledger pane, with a grip handle.
export const NarrativeAndLedger = () => (
  <ResizablePanelGroup
    direction="horizontal"
    style={{ height: 240, width: 460, border: "1px solid hsl(var(--border))", borderRadius: 8 }}
  >
    <ResizablePanel defaultSize={62}>
      <div style={{ padding: 16, fontSize: 14, lineHeight: 1.6, height: "100%" }}>
        <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 8 }}>Narrative</div>
        <p style={{ margin: 0 }}>
          The archive door answered to a name Mira had never spoken aloud. She
          stepped through before the tide could change its mind.
        </p>
      </div>
    </ResizablePanel>
    <ResizableHandle withHandle />
    <ResizablePanel defaultSize={38}>
      <div style={{ padding: 16, fontSize: 13, height: "100%" }}>
        <div style={{ opacity: 0.7, marginBottom: 8 }}>Ledger</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div>Mira Vance — present</div>
          <div>Cassius — nearby</div>
          <div>The Archivist — watching</div>
        </div>
      </div>
    </ResizablePanel>
  </ResizablePanelGroup>
);

// Vertical split: prose above, choices below.
export const ProseAndChoices = () => (
  <ResizablePanelGroup
    direction="vertical"
    style={{ height: 280, width: 380, border: "1px solid hsl(var(--border))", borderRadius: 8 }}
  >
    <ResizablePanel defaultSize={65}>
      <div style={{ padding: 16, fontSize: 14, lineHeight: 1.6, height: "100%" }}>
        <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 8 }}>Scene</div>
        <p style={{ margin: 0 }}>
          The choir's song rose from somewhere past the last dry room. Cassius
          held the lantern steady and waited for her to choose.
        </p>
      </div>
    </ResizablePanel>
    <ResizableHandle withHandle />
    <ResizablePanel defaultSize={35}>
      <div style={{ padding: 16, fontSize: 13, height: "100%" }}>
        <div style={{ opacity: 0.7, marginBottom: 8 }}>Choices</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div>1 · Follow the song into the dark</div>
          <div>2 · Seal the door and turn back</div>
        </div>
      </div>
    </ResizablePanel>
  </ResizablePanelGroup>
);
