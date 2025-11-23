import { useState, useEffect } from "react";
import { Loader2, Check, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";
import { toast } from "@/hooks/use-toast";

interface SeedOption {
    id: number;
    title: string;
    hook: string;
    conflict: string;
    starting_scene: string;
}

interface SeedPhaseProps {
    slot: number;
    onNext: (seedData: any) => void;
    initialData?: any;
}

export function SeedPhase({ slot, onNext, initialData }: SeedPhaseProps) {
    const [seeds, setSeeds] = useState<SeedOption[]>([]);
    const [selectedSeedId, setSelectedSeedId] = useState<number | null>(initialData?.id || null);
    const [isGenerating, setIsGenerating] = useState(false);

    // Simulate generation on mount if no seeds
    useEffect(() => {
        if (seeds.length === 0 && !isGenerating) {
            generateSeeds();
        }
    }, []);

    const generateSeeds = async () => {
        setIsGenerating(true);
        try {
            // Mock API call - in real app this would hit the backend
            // const res = await fetch("/api/story/new/setup/generate-seeds", ...);

            // Simulate delay
            await new Promise(resolve => setTimeout(resolve, 2000));

            const mockSeeds: SeedOption[] = [
                {
                    id: 1,
                    title: "The Data Heist",
                    hook: "You wake up with an encrypted shard in your pocket and no memory of how it got there.",
                    conflict: "Corporate hit squads are sweeping the block.",
                    starting_scene: "A grimy motel room in Sector 4, sirens wailing outside."
                },
                {
                    id: 2,
                    title: "Neon Shadows",
                    hook: "An old contact sends a distress signal from the quarantine zone.",
                    conflict: "The zone is locked down by military police.",
                    starting_scene: "The rain-slicked roof of a tenement building overlooking the wall."
                },
                {
                    id: 3,
                    title: "Ghost in the Machine",
                    hook: "Your cybernetics begin displaying messages from a dead netrunner.",
                    conflict: "You're losing control of your own augmentations.",
                    starting_scene: "A crowded ripperdoc clinic, mid-surgery."
                }
            ];
            setSeeds(mockSeeds);
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to generate story seeds.",
                variant: "destructive",
            });
        } finally {
            setIsGenerating(false);
        }
    };

    const recordSelectionMutation = useMutation({
        mutationFn: async (seed: SeedOption) => {
            const res = await fetch("/api/story/new/setup/record", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot,
                    seed: seed
                }),
            });

            if (!res.ok) throw new Error("Failed to record selection");
            return res.json();
        },
        onSuccess: (data, variables) => {
            onNext(variables);
        },
        onError: () => {
            toast({
                title: "Error",
                description: "Failed to save selection.",
                variant: "destructive",
            });
        },
    });

    const handleConfirm = () => {
        const seed = seeds.find(s => s.id === selectedSeedId);
        if (seed) {
            recordSelectionMutation.mutate(seed);
        }
    };

    if (isGenerating) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="font-mono text-sm text-muted-foreground">Calculating probability matrices...</p>
            </div>
        );
    }

    return (
        <div className="space-y-8 max-w-5xl mx-auto">
            <div className="text-center space-y-2">
                <h2 className="text-2xl font-mono text-primary terminal-glow">[SELECT INCITING INCIDENT]</h2>
                <p className="text-muted-foreground font-mono text-sm">
                    Choose the starting point for your narrative.
                </p>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
                {seeds.map((seed) => (
                    <Card
                        key={seed.id}
                        onClick={() => setSelectedSeedId(seed.id)}
                        className={cn(
                            "p-6 cursor-pointer transition-all duration-300 border-border bg-card/50 hover:bg-card hover:border-primary/50 relative overflow-hidden flex flex-col",
                            selectedSeedId === seed.id && "border-primary bg-primary/5 ring-1 ring-primary scale-105 z-10"
                        )}
                    >
                        <div className="space-y-4 flex-1">
                            <div className="flex items-start justify-between">
                                <h3 className="text-lg font-bold text-primary">{seed.title}</h3>
                                {selectedSeedId === seed.id && <Check className="h-5 w-5 text-primary" />}
                            </div>

                            <div className="space-y-2">
                                <p className="text-sm text-foreground/90 font-medium">{seed.hook}</p>
                                <p className="text-xs text-muted-foreground italic">{seed.conflict}</p>
                            </div>

                            <div className="pt-4 mt-auto border-t border-border/50">
                                <span className="text-[10px] font-mono text-accent uppercase tracking-wider">Starting Scene</span>
                                <p className="text-xs font-mono text-muted-foreground mt-1">{seed.starting_scene}</p>
                            </div>
                        </div>
                    </Card>
                ))}
            </div>

            <div className="flex justify-center pt-8">
                <Button
                    onClick={handleConfirm}
                    disabled={!selectedSeedId || recordSelectionMutation.isPending}
                    className="font-mono bg-primary/20 text-primary hover:bg-primary/30 border border-primary/50 terminal-glow h-12 px-8 text-lg"
                >
                    {recordSelectionMutation.isPending ? (
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    ) : (
                        <Sparkles className="mr-2 h-5 w-5" />
                    )}
                    BEGIN SIMULATION
                </Button>
            </div>
        </div>
    );
}
