import { useState, useEffect } from "react";
import { Loader2, MapPin, Globe, Navigation } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useMutation } from "@tanstack/react-query";
import { toast } from "@/hooks/use-toast";
import { useLocation } from "wouter";

interface LocationPhaseProps {
    slot: number;
    onNext: (locationData: any) => void;
    initialData?: any;
}

export function LocationPhase({ slot, onNext, initialData }: LocationPhaseProps) {
    const [isGenerating, setIsGenerating] = useState(true);
    const [locationData, setLocationData] = useState<any>(null);
    const [_, setLocation] = useLocation();

    useEffect(() => {
        generateLocation();
    }, []);

    const generateLocation = async () => {
        try {
            // Mock API call
            await new Promise(resolve => setTimeout(resolve, 3000));

            const mockLocation = {
                layer: { name: "Neo-Veridia", type: "City-State" },
                zone: { name: "Sector 4 (The Rust Belt)", type: "Industrial District" },
                place: {
                    name: "The Neon Lotus Motel",
                    type: "Residential",
                    coordinates: { lat: 34.0522, lng: -118.2437 }
                }
            };
            setLocationData(mockLocation);
            setIsGenerating(false);
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to generate location data.",
                variant: "destructive",
            });
        }
    };

    const finalizeMutation = useMutation({
        mutationFn: async () => {
            // Finalize setup
            const res = await fetch("/api/story/new/slot/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ slot }),
            });

            if (!res.ok) throw new Error("Failed to activate slot");
            return res.json();
        },
        onSuccess: () => {
            toast({
                title: "Initialization Complete",
                description: "Entering narrative interface...",
            });
            // Redirect to main app
            setTimeout(() => {
                window.location.href = "/"; // Force reload to clear wizard state
            }, 1000);
        },
        onError: () => {
            toast({
                title: "Error",
                description: "Failed to finalize setup.",
                variant: "destructive",
            });
        },
    });

    if (isGenerating) {
        return (
            <div className="flex flex-col items-center justify-center h-96 space-y-6">
                <div className="relative">
                    <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full animate-pulse" />
                    <Globe className="h-16 w-16 text-primary animate-spin-slow relative z-10" />
                </div>
                <div className="text-center space-y-2">
                    <h3 className="text-lg font-mono text-primary terminal-glow">CONSTRUCTING GEOGRAPHY</h3>
                    <p className="font-mono text-sm text-muted-foreground">
                        Triangulating coordinates... Generating terrain meshes...
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-8 max-w-3xl mx-auto animate-in fade-in zoom-in-95 duration-500">
            <div className="text-center space-y-2">
                <h2 className="text-2xl font-mono text-primary terminal-glow">[LOCATION LOCKED]</h2>
                <p className="text-muted-foreground font-mono text-sm">
                    Initial coordinates established.
                </p>
            </div>

            <Card className="p-8 border-primary/50 bg-card/50 terminal-scanlines relative overflow-hidden">
                {/* Map Grid Background Effect */}
                <div className="absolute inset-0 bg-[linear-gradient(rgba(0,255,0,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,0,0.05)_1px,transparent_1px)] bg-[size:20px_20px] pointer-events-none" />

                <div className="relative z-10 space-y-8">
                    <div className="flex items-center gap-4">
                        <div className="p-3 rounded-full bg-primary/10 border border-primary/30">
                            <Globe className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <span className="text-xs font-mono text-muted-foreground">WORLD LAYER</span>
                            <h3 className="text-xl font-bold text-foreground">{locationData.layer.name}</h3>
                        </div>
                    </div>

                    <div className="flex items-center gap-4 pl-8 border-l-2 border-primary/20">
                        <div className="p-3 rounded-full bg-primary/10 border border-primary/30">
                            <MapPin className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <span className="text-xs font-mono text-muted-foreground">ZONE</span>
                            <h3 className="text-xl font-bold text-foreground">{locationData.zone.name}</h3>
                        </div>
                    </div>

                    <div className="flex items-center gap-4 pl-16 border-l-2 border-primary/20">
                        <div className="p-3 rounded-full bg-primary/10 border border-primary/30">
                            <Navigation className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <span className="text-xs font-mono text-muted-foreground">STARTING LOCATION</span>
                            <h3 className="text-2xl font-bold text-primary terminal-glow">{locationData.place.name}</h3>
                            <p className="font-mono text-xs text-accent mt-1">
                                {locationData.place.coordinates.lat.toFixed(4)}, {locationData.place.coordinates.lng.toFixed(4)}
                            </p>
                        </div>
                    </div>
                </div>
            </Card>

            <div className="flex justify-center pt-4">
                <Button
                    onClick={() => finalizeMutation.mutate()}
                    disabled={finalizeMutation.isPending}
                    className="font-mono bg-primary text-primary-foreground hover:bg-primary/90 h-14 px-10 text-lg shadow-[0_0_20px_rgba(0,255,0,0.3)] hover:shadow-[0_0_30px_rgba(0,255,0,0.5)] transition-all"
                >
                    {finalizeMutation.isPending ? (
                        <>
                            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                            FINALIZING...
                        </>
                    ) : (
                        "ENTER SIMULATION"
                    )}
                </Button>
            </div>
        </div>
    );
}
