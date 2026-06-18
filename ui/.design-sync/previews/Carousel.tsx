import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselPrevious,
  CarouselNext,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "nexus-ui";

// Chapter browser — a horizontal carousel of save-slot / chapter cards. Outer
// horizontal padding keeps the absolutely-positioned prev/next arrows in-frame.
export const ChapterReel = () => (
  <div style={{ padding: "8px 64px", maxWidth: 520 }}>
    <Carousel opts={{ align: "start" }}>
      <CarouselContent>
        {[
          {
            t: "Chapter Five",
            d: "The Tidewater Pact",
            p: "Mira signs in saltwater ink, not knowing the cost.",
          },
          {
            t: "Chapter Six",
            d: "Beneath the Stacks",
            p: "The Archive's lower floors flood on a schedule no one will explain.",
          },
          {
            t: "Chapter Seven",
            d: "The Drowned Archive",
            p: "Cassius withholds the tide table. Mira goes down anyway.",
          },
        ].map((c) => (
          <CarouselItem key={c.t}>
            <Card>
              <CardHeader>
                <CardTitle>{c.t}</CardTitle>
                <CardDescription>{c.d}</CardDescription>
              </CardHeader>
              <CardContent>
                <p style={{ margin: 0, color: "hsl(var(--muted-foreground))" }}>
                  {c.p}
                </p>
              </CardContent>
            </Card>
          </CarouselItem>
        ))}
      </CarouselContent>
      <CarouselPrevious />
      <CarouselNext />
    </Carousel>
  </div>
);

// Multi-up gallery — character portraits at one-third basis, showing the item
// basis override and a denser layout.
export const CastGallery = () => (
  <div style={{ padding: "8px 64px", maxWidth: 560 }}>
    <Carousel opts={{ align: "start" }}>
      <CarouselContent>
        {[
          { n: "Mira Vance", r: "Protagonist" },
          { n: "Cassius Holt", r: "Foil" },
          { n: "The Archivist", r: "Keeper" },
          { n: "Senator Okonkwo", r: "Patron" },
        ].map((c) => (
          <CarouselItem key={c.n} style={{ flexBasis: "50%" }}>
            <div
              style={{
                borderRadius: 10,
                border: "1px solid hsl(var(--border))",
                padding: 16,
                background:
                  "linear-gradient(160deg, hsl(var(--muted)), hsl(var(--background)))",
              }}
            >
              <div style={{ color: "hsl(var(--foreground))", fontSize: 15 }}>
                {c.n}
              </div>
              <div
                style={{ color: "hsl(var(--muted-foreground))", fontSize: 12 }}
              >
                {c.r}
              </div>
            </div>
          </CarouselItem>
        ))}
      </CarouselContent>
      <CarouselPrevious />
      <CarouselNext />
    </Carousel>
  </div>
);
