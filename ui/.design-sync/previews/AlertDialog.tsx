import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from "nexus-ui";

// Destructive confirmation — the canonical alert-dialog use: wiping an
// occupied save slot earns explicit friction.
export const WipeSlot = () => (
  <AlertDialog open>
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>Wipe Save Slot 04?</AlertDialogTitle>
        <AlertDialogDescription>
          This permanently erases "The Drowned Archive" — all 41 chapters,
          the cast ledger, and the world map. Once committed, the slot cannot
          be recovered.
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter style={{ gap: 12 }}>
        <AlertDialogCancel>Keep Story</AlertDialogCancel>
        <AlertDialogAction>Wipe Slot</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

// Lower-stakes confirmation reusing the same primitive — committing a chapter
// in Ironman mode is irreversible but routine.
export const CommitChapter = () => (
  <AlertDialog open>
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>Commit Chapter Seven?</AlertDialogTitle>
        <AlertDialogDescription>
          Ironman mode is on. Accepting this chapter freezes it into the
          permanent record — you won't be able to rewind past this point.
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter style={{ gap: 12 }}>
        <AlertDialogCancel>Keep Editing</AlertDialogCancel>
        <AlertDialogAction>Commit &amp; Continue</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);
