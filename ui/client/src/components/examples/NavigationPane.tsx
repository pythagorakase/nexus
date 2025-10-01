import { NavigationPane } from '../NavigationPane';

export default function NavigationPaneExample() {
  return (
    <div className="dark h-96">
      <NavigationPane
        currentChunk={2}
        onChunkSelect={(id) => console.log('Selected chunk:', id)}
      />
    </div>
  );
}
