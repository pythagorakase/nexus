import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  Button,
} from "nexus-ui";

export const WipeSlot = () => (
  <Dialog open modal={false}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Wipe Save Slot 04?</DialogTitle>
        <DialogDescription>
          This permanently deletes "The Drowned Archive" and all 41 chapters.
          This action cannot be undone.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter style={{ gap: 12 }}>
        <Button variant="outline">Cancel</Button>
        <Button variant="destructive">Wipe Slot</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

export const NewStory = () => (
  <Dialog open modal={false}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Begin a New Story</DialogTitle>
        <DialogDescription>
          Slot 03 is empty. The wizard will guide you through setting, cast, and
          opening scene before your first chapter is written.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter style={{ gap: 12 }}>
        <Button variant="outline">Not Yet</Button>
        <Button>Start Wizard</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);
