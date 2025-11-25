import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { NexusLayout } from "@/components/NexusLayout";
import NotFound from "@/pages/not-found";

import NewStoryPage from "@/pages/NewStoryPage";

function Router() {
  return (
    <Switch>
      <Route path="/" component={NewStoryPage} />
      <Route path="/nexus" component={NexusLayout} />
      <Route path="/new-story" component={NewStoryPage} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <ErrorBoundary>
          <Toaster />
          <Router />
        </ErrorBoundary>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
