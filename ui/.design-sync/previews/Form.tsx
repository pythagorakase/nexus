import * as React from "react";
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
  Input,
  Button,
} from "nexus-ui";
import { useForm } from "react-hook-form";

// Canonical react-hook-form composition: labeled fields with descriptions.
export const NewStoryForm = () => {
  const form = useForm({
    defaultValues: { title: "The Drowned Archive", protagonist: "Mira Vance" },
  });
  return (
    <Form {...form}>
      <form
        style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 380 }}
        onSubmit={(e) => e.preventDefault()}
      >
        <FormField
          control={form.control}
          name="title"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Story Title</FormLabel>
              <FormControl>
                <Input placeholder="Untitled Story" {...field} />
              </FormControl>
              <FormDescription>Shown on the save-slot card.</FormDescription>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="protagonist"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Protagonist</FormLabel>
              <FormControl>
                <Input placeholder="Point-of-view character" {...field} />
              </FormControl>
            </FormItem>
          )}
        />
        <Button type="submit">Begin Story</Button>
      </form>
    </Form>
  );
};

// Validation state: a field rendered with an error message.
export const WithError = () => {
  const form = useForm({ defaultValues: { setting: "" } });
  // Surface a validation error after mount so the destructive label + message
  // render statically in the captured cell.
  React.useEffect(() => {
    form.setError("setting", {
      type: "required",
      message: "A setting is required before the wizard can begin.",
    });
  }, [form]);
  return (
    <Form {...form}>
      <form
        style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 380 }}
        onSubmit={(e) => e.preventDefault()}
      >
        <FormField
          control={form.control}
          name="setting"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Setting</FormLabel>
              <FormControl>
                <Input placeholder="Where does the story take place?" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" variant="outline">
          Continue
        </Button>
      </form>
    </Form>
  );
};
