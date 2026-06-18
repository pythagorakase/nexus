import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "nexus-ui";

export const ChapterLog = () => (
  <Accordion type="single" collapsible defaultValue="ch-7" style={{ width: 420 }}>
    <AccordionItem value="ch-6">
      <AccordionTrigger>Chapter Six — The Drowned Archive</AccordionTrigger>
      <AccordionContent>
        Mira descended past the flood line, where the records had gone soft as
        bread. Whatever the Veil wanted buried here, it had not buried it deep
        enough.
      </AccordionContent>
    </AccordionItem>
    <AccordionItem value="ch-7">
      <AccordionTrigger>Chapter Seven — Spire Lights</AccordionTrigger>
      <AccordionContent>
        The rain hadn't stopped for three days. From the gantry, Cassius
        counted the spire lights as they bled across the wet glass, each one a
        promise he no longer trusted.
      </AccordionContent>
    </AccordionItem>
    <AccordionItem value="ch-8">
      <AccordionTrigger>Chapter Eight — The Archivist's Price</AccordionTrigger>
      <AccordionContent>
        Some names cost more to remember than to forget. The Archivist named
        hers, and the room went very quiet.
      </AccordionContent>
    </AccordionItem>
  </Accordion>
);

export const WorldSettings = () => (
  <Accordion type="multiple" defaultValue={["geography"]} style={{ width: 420 }}>
    <AccordionItem value="geography">
      <AccordionTrigger>Geography &amp; Climate</AccordionTrigger>
      <AccordionContent>
        A drowned coastal megacity built atop real-Earth topography, perpetually
        storm-lashed. Sea level continues to rise across the campaign.
      </AccordionContent>
    </AccordionItem>
    <AccordionItem value="factions">
      <AccordionTrigger>Factions &amp; Powers</AccordionTrigger>
      <AccordionContent>
        Three powers contest the spires: the Cartel of Lamps, the Tidewardens,
        and the silent custodians of the Veil itself.
      </AccordionContent>
    </AccordionItem>
  </Accordion>
);
