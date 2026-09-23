import { useQuery } from "@tanstack/react-query";
import { Link, Redirect } from "wouter";
import { NewStoryWizard } from "@/components/NewStoryWizard/WizardShell";
import { Button } from "@/components/ui/button";
import { getActiveSlot } from "@/lib/active-slot";
import { getSlotState } from "@/lib/narrative-api";

/** Resolve the remembered slot's current mode before opening it. */
export default function ContinuePage() {
  const slot = getActiveSlot();
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["continue-slot", slot],
    queryFn: () => getSlotState(slot!),
    enabled: slot !== null,
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  if (slot === null) return <Redirect to="/new-story" replace />;
  if (isError) {
    return (
      <main className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center gap-4">
        <p role="alert">Could not load Memory Slot {slot}. Please try again.</p>
        <Button onClick={() => refetch()}>Retry</Button>
        <Button variant="ghost" asChild><Link href="/new-story">Load another slot</Link></Button>
      </main>
    );
  }
  if (isFetching || !data) {
    return <main className="min-h-screen bg-background text-foreground grid place-items-center" role="status">Loading Memory Slot {slot}…</main>;
  }
  if (data.is_empty) return <Redirect to="/new-story" replace />;
  if (data.is_wizard_mode) return <NewStoryWizard key={slot} resumeSlot={slot} />;
  return <Redirect to="/nexus" replace />;
}
