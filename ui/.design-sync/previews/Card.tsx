import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Button,
} from "nexus-ui";

// Canonical compound composition: a save-slot card with all sub-parts.
export const Default = () => (
  <Card style={{ maxWidth: 380 }}>
    <CardHeader>
      <CardTitle>Save Slot 02</CardTitle>
      <CardDescription>The Veil — Chapter Seven</CardDescription>
    </CardHeader>
    <CardContent>
      <p style={{ margin: 0 }}>
        The rain hadn't stopped for three days. Mira watched the spire lights
        bleed across the wet glass and counted the seconds between thunder.
      </p>
    </CardContent>
    <CardFooter style={{ gap: 12 }}>
      <Button>Continue</Button>
      <Button variant="outline">Load</Button>
    </CardFooter>
  </Card>
);

// Minimal composition: header + content only.
export const Simple = () => (
  <Card style={{ maxWidth: 320 }}>
    <CardHeader>
      <CardTitle>Cast</CardTitle>
      <CardDescription>3 characters in scene</CardDescription>
    </CardHeader>
    <CardContent>
      <p style={{ margin: 0 }}>Mira · Cassius · The Archivist</p>
    </CardContent>
  </Card>
);
