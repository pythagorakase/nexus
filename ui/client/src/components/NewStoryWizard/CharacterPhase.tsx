import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, RefreshCw, Check, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import { useMutation } from "@tanstack/react-query";
import { toast } from "@/hooks/use-toast";

const characterSchema = z.object({
    name: z.string().optional(),
    archetype: z.string().min(1, "Archetype is required"),
    background: z.string().optional(),
    key_trait: z.string().optional(),
});

type CharacterFormValues = z.infer<typeof characterSchema>;

interface CharacterPhaseProps {
    slot: number;
    onNext: (characterData: any) => void;
    initialData?: any;
}

export function CharacterPhase({ slot, onNext, initialData }: CharacterPhaseProps) {
    const [generatedCharacter, setGeneratedCharacter] = useState<any>(initialData || null);

    const form = useForm<CharacterFormValues>({
        resolver: zodResolver(characterSchema),
        defaultValues: {
            name: "",
            archetype: "Street Samurai",
            background: "",
            key_trait: "",
        },
    });

    const generateMutation = useMutation({
        mutationFn: async (values: CharacterFormValues) => {
            const res = await fetch("/api/story/new/setup/record", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot,
                    character: {
                        preferences: values,
                    }
                }),
            });

            if (!res.ok) {
                const error = await res.text();
                throw new Error(error || "Failed to generate character");
            }

            return res.json();
        },
        onSuccess: (data) => {
            // Mocking generated data
            const mockCharacter = {
                name: form.getValues().name || "Kaelen Vane",
                archetype: form.getValues().archetype,
                background: "Former corporate security detail, burned after a botched extraction operation. Now works the shadows of the lower districts.",
                stats: { STR: 8, DEX: 12, INT: 10, TECH: 14 },
                skills: ["Hacking", "Small Arms", "Stealth", "Corporate Protocol"],
                ...form.getValues()
            };
            setGeneratedCharacter(mockCharacter);
            toast({
                title: "Character Generated",
                description: "Protagonist profile created.",
            });
        },
        onError: (error) => {
            toast({
                title: "Generation Failed",
                description: error instanceof Error ? error.message : "Unknown error",
                variant: "destructive",
            });
        },
    });

    const onSubmit = (values: CharacterFormValues) => {
        generateMutation.mutate(values);
    };

    const handleConfirm = () => {
        if (generatedCharacter) {
            onNext(generatedCharacter);
        }
    };

    if (generatedCharacter) {
        return (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="text-center space-y-2 mb-8">
                    <h2 className="text-2xl font-mono text-primary terminal-glow">[PROTAGONIST PROFILE]</h2>
                    <p className="text-muted-foreground font-mono text-sm">
                        Review character specification.
                    </p>
                </div>

                <div className="grid md:grid-cols-3 gap-6">
                    {/* Portrait / Stats Column */}
                    <Card className="p-6 border-primary/50 bg-card/50 terminal-scanlines flex flex-col items-center text-center space-y-4">
                        <div className="w-32 h-32 rounded-full bg-muted/20 flex items-center justify-center border-2 border-primary/50 terminal-glow">
                            <User className="w-16 h-16 text-primary/80" />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-primary">{generatedCharacter.name}</h3>
                            <p className="text-sm text-accent font-mono">{generatedCharacter.archetype}</p>
                        </div>

                        <div className="w-full pt-4 border-t border-border">
                            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                                {Object.entries(generatedCharacter.stats || {}).map(([stat, val]: [string, any]) => (
                                    <div key={stat} className="flex justify-between">
                                        <span className="text-muted-foreground">{stat}:</span>
                                        <span className="text-foreground font-bold">{val}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </Card>

                    {/* Details Column */}
                    <Card className="md:col-span-2 p-6 border-primary/50 bg-card/50 terminal-scanlines space-y-6">
                        <div>
                            <span className="text-xs font-mono text-primary mb-1 block">BACKGROUND</span>
                            <p className="text-sm leading-relaxed text-foreground/90">
                                {generatedCharacter.background}
                            </p>
                        </div>

                        <div>
                            <span className="text-xs font-mono text-primary mb-1 block">SKILLS & ABILITIES</span>
                            <div className="flex flex-wrap gap-2">
                                {generatedCharacter.skills?.map((skill: string, i: number) => (
                                    <span key={i} className="px-2 py-1 rounded bg-accent/10 text-accent text-xs font-mono border border-accent/20">
                                        {skill}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </Card>
                </div>

                <div className="flex justify-end gap-4">
                    <Button
                        variant="outline"
                        onClick={() => setGeneratedCharacter(null)}
                        className="font-mono"
                    >
                        <RefreshCw className="mr-2 h-4 w-4" />
                        REGENERATE
                    </Button>
                    <Button
                        onClick={handleConfirm}
                        className="font-mono bg-primary/20 text-primary hover:bg-primary/30 border border-primary/50 terminal-glow"
                    >
                        <Check className="mr-2 h-4 w-4" />
                        CONFIRM CHARACTER
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto space-y-8">
            <div className="text-center space-y-2">
                <h2 className="text-2xl font-mono text-primary terminal-glow">[DESIGN PROTAGONIST]</h2>
                <p className="text-muted-foreground font-mono text-sm">
                    Define the core attributes of the main character.
                </p>
            </div>

            <Form {...form}>
                <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                        <FormField
                            control={form.control}
                            name="name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel className="font-mono text-xs text-primary">NAME (OPTIONAL)</FormLabel>
                                    <FormControl>
                                        <Input {...field} className="font-mono" placeholder="Leave blank to generate" />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <FormField
                            control={form.control}
                            name="archetype"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel className="font-mono text-xs text-primary">ARCHETYPE</FormLabel>
                                    <FormControl>
                                        <Input {...field} className="font-mono" placeholder="e.g. Netrunner, Detective" />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                    </div>

                    <FormField
                        control={form.control}
                        name="background"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel className="font-mono text-xs text-primary">BACKGROUND HINTS</FormLabel>
                                <FormControl>
                                    <Textarea
                                        {...field}
                                        className="font-mono min-h-[80px]"
                                        placeholder="Brief history or origin..."
                                    />
                                </FormControl>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <FormField
                        control={form.control}
                        name="key_trait"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel className="font-mono text-xs text-primary">KEY TRAIT / FLAW</FormLabel>
                                <FormControl>
                                    <Input {...field} className="font-mono" placeholder="e.g. Paranoia, Cybernetic Arm" />
                                </FormControl>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <Button
                        type="submit"
                        className="w-full font-mono bg-primary/20 text-primary hover:bg-primary/30 border border-primary/50 terminal-glow h-12 text-lg"
                        disabled={generateMutation.isPending}
                    >
                        {generateMutation.isPending ? (
                            <>
                                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                                GENERATING PROFILE...
                            </>
                        ) : (
                            "GENERATE CHARACTER"
                        )}
                    </Button>
                </form>
            </Form>
        </div>
    );
}
