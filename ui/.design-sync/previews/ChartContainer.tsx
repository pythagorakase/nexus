import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
} from "nexus-ui";
import {
  Bar,
  BarChart,
  Area,
  AreaChart,
  CartesianGrid,
  XAxis,
} from "recharts";

const wordData = [
  { chapter: "Ch 3", words: 3120 },
  { chapter: "Ch 4", words: 4480 },
  { chapter: "Ch 5", words: 2960 },
  { chapter: "Ch 6", words: 5210 },
  { chapter: "Ch 7", words: 6040 },
];

const wordConfig = {
  words: { label: "Words", color: "hsl(var(--primary))" },
};

// Bar chart — per-chapter word counts, the canonical ChartContainer use with a
// themed bar series and a styled tooltip.
export const ChapterWordCount = () => (
  <div style={{ width: 460 }}>
    <ChartContainer config={wordConfig}>
      <BarChart data={wordData}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="chapter"
          tickLine={false}
          tickMargin={10}
          axisLine={false}
        />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="words" fill="var(--color-words)" radius={4} />
      </BarChart>
    </ChartContainer>
  </div>
);

const paceData = [
  { chapter: "Ch 3", tension: 32, intimacy: 48 },
  { chapter: "Ch 4", tension: 55, intimacy: 40 },
  { chapter: "Ch 5", tension: 47, intimacy: 62 },
  { chapter: "Ch 6", tension: 78, intimacy: 35 },
  { chapter: "Ch 7", tension: 90, intimacy: 28 },
];

const paceConfig = {
  tension: { label: "Tension", color: "hsl(var(--primary))" },
  intimacy: { label: "Intimacy", color: "hsl(var(--muted-foreground))" },
};

// Stacked area chart — two themed series with a legend, exercising the
// multi-series config + ChartLegendContent.
export const PacingCurve = () => (
  <div style={{ width: 460 }}>
    <ChartContainer config={paceConfig}>
      <AreaChart data={paceData}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="chapter"
          tickLine={false}
          tickMargin={10}
          axisLine={false}
        />
        <ChartTooltip content={<ChartTooltipContent />} />
        <ChartLegend content={<ChartLegendContent />} />
        <Area
          dataKey="intimacy"
          type="natural"
          fill="var(--color-intimacy)"
          fillOpacity={0.4}
          stroke="var(--color-intimacy)"
          stackId="a"
        />
        <Area
          dataKey="tension"
          type="natural"
          fill="var(--color-tension)"
          fillOpacity={0.4}
          stroke="var(--color-tension)"
          stackId="a"
        />
      </AreaChart>
    </ChartContainer>
  </div>
);
