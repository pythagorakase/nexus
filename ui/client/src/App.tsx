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
import DevMarkdownPreview from "@/pages/DevMarkdownPreview";
import { NexusLayout } from "@/components/nexus";

function Router() {
  return (
    <Switch>
      <Route path="/" component={SplashPage} />
      <Route path="/new-story" component={NewStoryPage} />
      <Route path="/nexus" component={NexusLayout} />
      {/* Dev-only harness for narrative markdown rendering. */}
      {import.meta.env.DEV && (
        <Route path="/dev/markdown" component={DevMarkdownPreview} />
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
