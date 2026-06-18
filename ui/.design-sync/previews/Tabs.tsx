import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "nexus-ui";

export const StoryPanels = () => (
  <Tabs defaultValue="narrative" style={{ width: 460 }}>
    <TabsList>
      <TabsTrigger value="narrative">Narrative</TabsTrigger>
      <TabsTrigger value="cast">Cast</TabsTrigger>
      <TabsTrigger value="map">Map</TabsTrigger>
      <TabsTrigger value="ledger">Ledger</TabsTrigger>
    </TabsList>
    <TabsContent value="narrative" style={{ paddingTop: 16, fontSize: 14 }}>
      The rain hadn't stopped for three days. Mira watched the spire lights
      bleed across the wet glass and counted the seconds between thunder.
    </TabsContent>
    <TabsContent value="cast" style={{ paddingTop: 16, fontSize: 14 }}>
      Mira, Cassius, and the Archivist are present in this scene.
    </TabsContent>
    <TabsContent value="map" style={{ paddingTop: 16, fontSize: 14 }}>
      Current location: The Spires, eastern flood district.
    </TabsContent>
    <TabsContent value="ledger" style={{ paddingTop: 16, fontSize: 14 }}>
      No open debts. One unresolved promise to the Tidewardens.
    </TabsContent>
  </Tabs>
);

export const SettingsTabs = () => (
  <Tabs defaultValue="model" style={{ width: 420 }}>
    <TabsList>
      <TabsTrigger value="model">Model</TabsTrigger>
      <TabsTrigger value="context">Context Length</TabsTrigger>
      <TabsTrigger value="theme">Theme</TabsTrigger>
    </TabsList>
    <TabsContent value="model" style={{ paddingTop: 16, fontSize: 14 }}>
      Storyteller routed to the frontier author model. Local curators handle
      retrieval and continuity.
    </TabsContent>
    <TabsContent value="context" style={{ paddingTop: 16, fontSize: 14 }}>
      Warm slice holds the last twelve chapters; long-term memory fills the
      rest on demand.
    </TabsContent>
    <TabsContent value="theme" style={{ paddingTop: 16, fontSize: 14 }}>
      Veil — a dark, storm-lit palette with copper accents.
    </TabsContent>
  </Tabs>
);
