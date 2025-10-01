import { NarrativePane, type NarrativeChunk } from '../NarrativePane';

const mockChunks: NarrativeChunk[] = [
  {
    id: 1,
    season: 1,
    episode: 1,
    scene: 1,
    sections: [
      {
        type: "storyteller",
        content: "The neon-lit streets of Neo-Tokyo stretched before you, rain-slicked and gleaming with a thousand reflections. Your cybernetic hand flickered with a diagnostic warning—something was wrong with the neural interface."
      },
      {
        type: "you",
        content: "I check the diagnostic readout on my arm panel."
      },
      {
        type: "storyteller",
        content: "The holographic display materializes above your wrist, cascading lines of code revealing the source: an unauthorized access attempt from an unknown netrunner. Your handler's voice crackles through your cochlear implant: 'Alex, you've got a tail. Corporate netrunner, high-grade ICE. Get to the safe house, now.'"
      }
    ],
    metadata: {
      location: "Downtown Neo-Tokyo",
      timestamp: "2087-03-15 23:47",
      characters: ["Alex", "Handler"]
    }
  }
];

export default function NarrativePaneExample() {
  return (
    <div className="dark h-96">
      <NarrativePane
        chunks={mockChunks}
        currentChunk={1}
        mode="read"
      />
    </div>
  );
}
