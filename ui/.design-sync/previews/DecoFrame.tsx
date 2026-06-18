import { DecoFrame, Card, CardHeader, CardTitle, CardDescription, CardContent } from "nexus-ui";
// DecoFrame adds Art Deco corners around its children — corners render in the
// Gilded theme, so the card is shown there.
if (typeof window !== "undefined") window.localStorage?.setItem("nexus-theme", "gilded");

export const FramedCard = () => (
  <DecoFrame cornerSize={26}>
    <Card style={{ width: 320 }}>
      <CardHeader>
        <CardTitle>The Gilded Hour</CardTitle>
        <CardDescription>Chapter Seven</CardDescription>
      </CardHeader>
      <CardContent>
        <p style={{ margin: 0 }}>Brass light pooled on the parquet as the orchestra tuned below.</p>
      </CardContent>
    </Card>
  </DecoFrame>
);
