import {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
} from "nexus-ui";

// Save-slot roster: a full multi-row table with header, selected row, and footer.
export const SaveSlots = () => (
  <div style={{ width: 620 }}>
    <Table>
      <TableCaption>Five save slots · two occupied</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>Slot</TableHead>
          <TableHead>Story</TableHead>
          <TableHead>Chapter</TableHead>
          <TableHead style={{ textAlign: "right" }}>Last Saved</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell style={{ fontWeight: 600 }}>01</TableCell>
          <TableCell>The Drowned Archive</TableCell>
          <TableCell>41</TableCell>
          <TableCell style={{ textAlign: "right" }}>2 days ago</TableCell>
        </TableRow>
        <TableRow data-state="selected">
          <TableCell style={{ fontWeight: 600 }}>02</TableCell>
          <TableCell>The Veil</TableCell>
          <TableCell>7</TableCell>
          <TableCell style={{ textAlign: "right" }}>3 minutes ago</TableCell>
        </TableRow>
        <TableRow>
          <TableCell style={{ fontWeight: 600 }}>03</TableCell>
          <TableCell style={{ opacity: 0.6 }}>Empty</TableCell>
          <TableCell style={{ opacity: 0.6 }}>—</TableCell>
          <TableCell style={{ textAlign: "right", opacity: 0.6 }}>—</TableCell>
        </TableRow>
      </TableBody>
      <TableFooter>
        <TableRow>
          <TableCell colSpan={3}>Total Chapters</TableCell>
          <TableCell style={{ textAlign: "right" }}>48</TableCell>
        </TableRow>
      </TableFooter>
    </Table>
  </div>
);

// Character ledger: a compact table without footer.
export const Cast = () => (
  <div style={{ width: 560 }}>
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Character</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Status</TableHead>
          <TableHead style={{ textAlign: "right" }}>First Seen</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell style={{ fontWeight: 600 }}>Mira</TableCell>
          <TableCell>Archivist's Apprentice</TableCell>
          <TableCell>In Scene</TableCell>
          <TableCell style={{ textAlign: "right" }}>Ch. 1</TableCell>
        </TableRow>
        <TableRow>
          <TableCell style={{ fontWeight: 600 }}>Cassius</TableCell>
          <TableCell>Tidewarden</TableCell>
          <TableCell>Waiting</TableCell>
          <TableCell style={{ textAlign: "right" }}>Ch. 3</TableCell>
        </TableRow>
        <TableRow>
          <TableCell style={{ fontWeight: 600 }}>The Archivist</TableCell>
          <TableCell>Mentor</TableCell>
          <TableCell>Offstage</TableCell>
          <TableCell style={{ textAlign: "right" }}>Ch. 1</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </div>
);
