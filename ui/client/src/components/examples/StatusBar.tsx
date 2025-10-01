import { StatusBar } from '../StatusBar';

export default function StatusBarExample() {
  return (
    <div className="dark">
      <StatusBar
        model="Llama 3.3"
        season={1}
        episode={1}
        scene={2}
        apexStatus="READY"
        isStoryMode={true}
        onHamburgerClick={() => console.log('Hamburger clicked')}
      />
    </div>
  );
}
