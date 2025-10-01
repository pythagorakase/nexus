import { CommandBar } from '../CommandBar';

export default function CommandBarExample() {
  return (
    <div className="dark">
      <CommandBar
        onCommand={(cmd) => console.log('Command:', cmd)}
        placeholder="continue the story"
        userPrefix="ALEX"
      />
    </div>
  );
}
