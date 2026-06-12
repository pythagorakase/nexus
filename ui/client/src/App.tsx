import { lazy, Suspense } from "react";
import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { FontProvider } from "@/contexts/FontContext";
import { ModelProvider } from "@/contexts/ModelContext";
import NotFound from "@/pages/not-found";
import SplashPage from "@/pages/SplashPage";
import NewStoryPage from "@/pages/NewStoryPage";
import { NexusLayout } from "@/components/nexus";

// Dev-only markdown harness: lazy + DEV-guarded so the module (and its
// embedded fixture text) never reaches the production bundle.
const DevMarkdownPreview = import.meta.env.DEV
  ? lazy(() => import("@/pages/DevMarkdownPreview"))
  : null;

function Router() {
  return (
    <Switch>
      <Route path="/" component={SplashPage} />
      <Route path="/new-story" component={NewStoryPage} />
      <Route path="/nexus" component={NexusLayout} />
      {DevMarkdownPreview && (
        <Route path="/dev/markdown">
          <Suspense fallback={null}>
            <DevMarkdownPreview />
          </Suspense>
        </Route>
      )}
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  // QueryClientProvider wraps the theme/font contexts so they can hydrate
  // from (and persist through) the GET/PATCH /api/settings query.
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <FontProvider>
          <ModelProvider>
            <TooltipProvider>
              <ErrorBoundary>
                <Toaster />
                <Router />
              </ErrorBoundary>
            </TooltipProvider>
          </ModelProvider>
        </FontProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
