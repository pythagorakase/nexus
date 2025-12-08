import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { FontProvider } from "@/contexts/FontContext";
import { ModelProvider } from "@/contexts/ModelContext";
import { NexusLayout } from "@/components/NexusLayout";
import NotFound from "@/pages/not-found";
import SplashPage from "@/pages/SplashPage";
import NewStoryPage from "@/pages/NewStoryPage";

function Router() {
  return (
    <Switch>
      <Route path="/" component={SplashPage} />
      <Route path="/nexus" component={NexusLayout} />
      <Route path="/new-story" component={NewStoryPage} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ThemeProvider>
      <FontProvider>
        <ModelProvider>
          <QueryClientProvider client={queryClient}>
            <TooltipProvider>
              <ErrorBoundary>
                <Toaster />
                <Router />
              </ErrorBoundary>
            </TooltipProvider>
          </QueryClientProvider>
        </ModelProvider>
      </FontProvider>
    </ThemeProvider>
  );
}

export default App;
