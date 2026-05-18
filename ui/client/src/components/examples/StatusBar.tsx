import { StatusBar } from '../StatusBar';

export default function StatusBarExample() {
  return (
    <div className="dark">
      <StatusBar
        model="Llama 3.3"
        apexStatus="READY"
        isStoryMode={true}
      />
    </div>
  );
}
