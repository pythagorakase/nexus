import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, RefreshCw, Check } from "lucide-react";
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
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useMutation } from "@tanstack/react-query";
import { toast } from "@/hooks/use-toast";

const settingSchema = z.object({
    genre: z.string().min(1, "Genre is required"),
    tone: z.string().min(1, "Tone is required"),
    tech_level: z.string().min(1, "Tech level is required"),
    additional_notes: z.string().optional(),
});

type SettingFormValues = z.infer<typeof settingSchema>;

interface SettingPhaseProps {
    slot: number;
    onNext: (settingData: any) => void;
    initialData?: any;
}

export function SettingPhase({ slot, onNext, initialData }: SettingPhaseProps) {
    const [generatedSetting, setGeneratedSetting] = useState<any>(initialData || null);

    const form = useForm<SettingFormValues>({
        resolver: zodResolver(settingSchema),
        defaultValues: {
            genre: "Cyberpunk",
            tone: "Gritty",
            tech_level: "High Tech / Low Life",
            additional_notes: "",
        },
    });

    const generateMutation = useMutation({
        mutationFn: async (values: SettingFormValues) => {
            const res = await fetch("/api/story/new/setup/record", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot,
                    setting: {
                        preferences: values,
                        // In a real implementation, we'd probably send just preferences 
                        // and let the backend generate the full setting card
                    }
                }),
            });

            if (!res.ok) {
                const error = await res.text();
                throw new Error(error || "Failed to generate setting");
            }

            return res.json();
        },
        onSuccess: (data) => {
            // Mocking the generated data structure for now since the backend 
            // returns { status: "recorded", slot: number }
            // In a real app, we'd fetch the generated setting or the backend would return it
            const mockSetting = {
                name: "Neo-Veridia Prime",
                description: "A sprawling metropolis built on the ruins of the old world, where neon lights obscure the decay beneath.",
                themes: ["Transhumanism", "Corporate Greed", "Digital Decay"],
                ...form.getValues()
            };
            setGeneratedSetting(mockSetting);
            toast({
                title: "World Generated",
                description: "Setting parameters established.",
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

    const onSubmit = (values: SettingFormValues) => {
        generateMutation.mutate(values);
    };

    const handleConfirm = () => {
        if (generatedSetting) {
            onNext(generatedSetting);
        }
    };

    if (generatedSetting) {
        return (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="text-center space-y-2 mb-8">
                    <h2 className="text-2xl font-mono text-primary terminal-glow">[WORLD PARAMETERS ESTABLISHED]</h2>
                    <p className="text-muted-foreground font-mono text-sm">
                        Review generated setting data.
                    </p>
                </div>

                <Card className="p-6 border-primary/50 bg-card/50 terminal-scanlines relative overflow-hidden">
                    <div className="space-y-6 relative z-10">
                        <div>
                            <h3 className="text-lg font-bold text-primary mb-2">{generatedSetting.name}</h3>
                            <p className="text-foreground/90 leading-relaxed">{generatedSetting.description}</p>
                        </div>

                        <div className="grid grid-cols-2 gap-4 text-sm font-mono">
                            <div>
                                <span className="text-muted-foreground">GENRE:</span>
                                <span className="ml-2 text-accent">{generatedSetting.genre}</span>
                            </div>
                            <div>
                                <span className="text-muted-foreground">TECH LEVEL:</span>
                                <span className="ml-2 text-accent">{generatedSetting.tech_level}</span>
                            </div>
                            <div>
                                <span className="text-muted-foreground">TONE:</span>
                                <span className="ml-2 text-accent">{generatedSetting.tone}</span>
                            </div>
                        </div>

                        <div>
                            <span className="text-muted-foreground font-mono text-sm block mb-2">THEMES:</span>
                            <div className="flex flex-wrap gap-2">
                                {generatedSetting.themes.map((theme: string, i: number) => (
                                    <span key={i} className="px-2 py-1 rounded bg-primary/10 text-primary text-xs font-mono border border-primary/20">
                                        {theme}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </div>
                </Card>

                <div className="flex justify-end gap-4">
                    <Button
                        variant="outline"
                        onClick={() => setGeneratedSetting(null)}
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
                        CONFIRM SETTING
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto space-y-8">
            <div className="text-center space-y-2">
                <h2 className="text-2xl font-mono text-primary terminal-glow">[INITIALIZE WORLD STATE]</h2>
                <p className="text-muted-foreground font-mono text-sm">
                    Define the parameters for the narrative environment.
                </p>
            </div>

            <Form {...form}>
                <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
                    <FormField
                        control={form.control}
                        name="genre"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel className="font-mono text-xs text-primary">GENRE</FormLabel>
                                <Select onValueChange={field.onChange} defaultValue={field.value}>
                                    <FormControl>
                                        <SelectTrigger className="font-mono">
                                            <SelectValue placeholder="Select genre" />
                                        </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                        <SelectItem value="Cyberpunk">Cyberpunk</SelectItem>
                                        <SelectItem value="Post-Apocalyptic">Post-Apocalyptic</SelectItem>
                                        <SelectItem value="Space Opera">Space Opera</SelectItem>
                                        <SelectItem value="Urban Fantasy">Urban Fantasy</SelectItem>
                                        <SelectItem value="Tech Noir">Tech Noir</SelectItem>
                                    </SelectContent>
                                </Select>
                                <FormMessage />
                            </FormItem>
                        )}
                    />

                    <div className="grid grid-cols-2 gap-4">
                        <FormField
                            control={form.control}
                            name="tone"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel className="font-mono text-xs text-primary">TONE</FormLabel>
                                    <FormControl>
                                        <Input {...field} className="font-mono" placeholder="e.g. Gritty, Hopeful" />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <FormField
                            control={form.control}
                            name="tech_level"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel className="font-mono text-xs text-primary">TECH LEVEL</FormLabel>
                                    <FormControl>
                                        <Input {...field} className="font-mono" placeholder="e.g. High Tech / Low Life" />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                    </div>

                    <FormField
                        control={form.control}
                        name="additional_notes"
                        render={({ field }) => (
                            <FormItem>
                                <FormLabel className="font-mono text-xs text-primary">ADDITIONAL PARAMETERS</FormLabel>
                                <FormControl>
                                    <Textarea
                                        {...field}
                                        className="font-mono min-h-[100px]"
                                        placeholder="Specific details, themes, or constraints..."
                                    />
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
                                GENERATING WORLD STATE...
                            </>
                        ) : (
                            "GENERATE SETTING"
                        )}
                    </Button>
                </form>
            </Form>
        </div>
    );
}
