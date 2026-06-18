import { ErrorBoundary, Card, CardHeader, CardTitle, CardContent } from "nexus-ui";

// ErrorBoundary is a transparent wrapper: it renders its children normally and
// only swaps to a recovery fallback if a descendant throws during render. We show
// the healthy pass-through — a throwing demo cell renders thin in the all-cells
// validator pass, and the boundary has no visual of its own.
export const Healthy = () => (
  <div style={{ width: 460 }}>
    <ErrorBoundary>
      <Card>
        <CardHeader>
          <CardTitle>Chapter Seven — The Spire Lights</CardTitle>
        </CardHeader>
        <CardContent>
          <p style={{ margin: 0 }}>
            The skiff cut a slow wake across the drowned plaza, lantern-light
            trembling on the water as the Spire rose ahead.
          </p>
        </CardContent>
      </Card>
    </ErrorBoundary>
  </div>
);
