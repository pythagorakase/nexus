import { useState } from "react";
import type { CSSProperties } from "react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import type { CognitionSourceNodeVM, CognitionTraceVM } from "./types";

const SECTION_LABEL: CSSProperties = {
  fontSize: 8,
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "hsl(var(--muted-foreground))",
};

function EmptyRow() {
  return (
    <div
      className="font-mono"
      style={{ fontSize: 10, color: "hsl(var(--muted-foreground))", padding: 12 }}
    >
      —
    </div>
  );
}

function SourceNode({ node, depth = 0 }: { node: CognitionSourceNodeVM; depth?: number }) {
  return (
    <Collapsible defaultOpen>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="font-mono"
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: `3px 5px 3px ${6 + depth * 14}px`,
            border: 0,
            background: "transparent",
            color: "hsl(var(--foreground) / 0.85)",
            fontSize: 9,
            textAlign: "left",
          }}
        >
          <span style={{ color: "hsl(var(--muted-foreground))" }}>⌄</span>
          <Badge variant="outline" style={{ fontSize: 7.5 }}>
            {node.kind}
          </Badge>
          {node.label}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        {node.children.map((child) => (
          <SourceNode key={child.key} node={child} depth={depth + 1} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

function TraceTagChip({
  label,
  sourceKey,
  onHover,
}: {
  label: string;
  sourceKey: string;
  onHover: (key: string | null) => void;
}) {
  return (
    <span
      className="font-mono"
      onMouseEnter={() => onHover(sourceKey)}
      onMouseLeave={() => onHover(null)}
      style={{
        display: "inline-flex",
        border: "1px dashed hsl(var(--chart-2) / 0.6)",
        borderRadius: 99,
        padding: "1px 7px",
        fontSize: 8.5,
        color: "hsl(var(--chart-2))",
      }}
    >
      {label}
    </span>
  );
}

function AccountsTab({ vm, activeSource }: { vm: CognitionTraceVM; activeSource: string | null }) {
  return (
    <div data-screen-label="Cognition accounts" style={{ display: "grid", gap: 10 }}>
      <span className="font-mono" style={SECTION_LABEL}>
        Possession
      </span>
      {vm.accounts.length ? (
        <Accordion type="multiple">
          {vm.accounts.map((account) => (
            <AccordionItem
              key={account.key}
              value={account.key}
              style={{
                border: "1px solid hsl(var(--border))",
                borderColor:
                  activeSource === account.sourceKey
                    ? "hsl(var(--accent))"
                    : "hsl(var(--border))",
                padding: "0 10px",
              }}
            >
              <AccordionTrigger style={{ padding: "8px 0", textDecoration: "none" }}>
                <span style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span className="font-mono" style={{ fontSize: 9 }}>
                    {account.claim}
                  </span>
                  <span style={{ fontSize: 10.5 }}>{account.summary}</span>
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <div style={{ display: "grid", gap: 6 }}>
                  <span
                    className="font-mono"
                    style={{ fontSize: 8, color: "hsl(var(--muted-foreground))" }}
                  >
                    {account.meta}
                  </span>
                  <HoverCard>
                    <HoverCardTrigger asChild>
                      <button
                        type="button"
                        className="font-mono"
                        style={{
                          width: "fit-content",
                          border: 0,
                          background: "transparent",
                          color: "hsl(var(--chart-5))",
                          fontSize: 9,
                        }}
                      >
                        {account.sourceChunk}
                      </button>
                    </HoverCardTrigger>
                    <HoverCardContent className="font-mono text-xs">
                      {account.sourcePreview}
                    </HoverCardContent>
                  </HoverCard>
                  {account.chain.map((node) => (
                    <SourceNode key={node.key} node={node} />
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      ) : (
        <EmptyRow />
      )}
      <span className="font-mono" style={SECTION_LABEL}>
        Experience
      </span>
      {vm.experiences.length ? (
        vm.experiences.map((experience) => (
          <div
            key={experience.key}
            style={{
              border: "1px solid hsl(var(--border))",
              borderColor:
                activeSource === experience.sourceKey
                  ? "hsl(var(--accent))"
                  : "hsl(var(--border))",
              padding: 9,
              display: "grid",
              gap: 4,
            }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="font-mono" style={{ fontSize: 9 }}>
                {experience.id}
              </span>
              <Badge variant="outline">{experience.renderStatus}</Badge>
              <span
                className="font-mono"
                style={{ marginLeft: "auto", fontSize: 8.5 }}
              >
                {experience.salience}
              </span>
            </div>
            <span style={{ fontSize: 10.5 }}>{experience.summary}</span>
            <HoverCard>
              <HoverCardTrigger asChild>
                <span
                  className="font-mono"
                  style={{ fontSize: 8, color: "hsl(var(--muted-foreground))" }}
                >
                  {experience.meta}
                </span>
              </HoverCardTrigger>
              <HoverCardContent className="font-mono whitespace-pre-line text-xs">
                {experience.sourcePreview}
              </HoverCardContent>
            </HoverCard>
          </div>
        ))
      ) : (
        <EmptyRow />
      )}
    </div>
  );
}

function RecallTab({
  vm,
  onHover,
}: {
  vm: CognitionTraceVM;
  onHover: (key: string | null) => void;
}) {
  return (
    <div data-screen-label="Cognition recall">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>source</TableHead>
            <TableHead>decision</TableHead>
            <TableHead>score</TableHead>
            <TableHead>components</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {vm.recalls.map((row) => (
            <TableRow key={row.key} style={{ borderStyle: "dashed" }}>
              <TableCell>
                <TraceTagChip label={row.sourceLabel} sourceKey={row.sourceKey} onHover={onHover} />
                <div style={{ fontSize: 9.5, marginTop: 4 }}>{row.summary}</div>
              </TableCell>
              <TableCell>
                <Badge variant={row.decision === "suppressed" ? "destructive" : "outline"}>
                  {row.decision}
                </Badge>
                <div className="font-mono" style={{ fontSize: 8, marginTop: 3 }}>
                  {row.reason}
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs">
                {row.score} / {row.threshold}
              </TableCell>
              <TableCell style={{ minWidth: 190 }}>
                {row.components.map((component) => (
                  <div key={component.label} style={{ display: "grid", gap: 2, marginBottom: 4 }}>
                    <div
                      className="font-mono"
                      style={{ display: "flex", fontSize: 7.5, justifyContent: "space-between" }}
                    >
                      <span>{component.label}</span>
                      <span>{component.value}</span>
                    </div>
                    <div
                      style={{
                        height: 3,
                        background: "hsl(var(--muted) / 0.3)",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: component.pct,
                          height: "100%",
                          background: "hsl(var(--chart-5))",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {!vm.recalls.length && <EmptyRow />}
    </div>
  );
}

function DisclosureTab({
  vm,
  onHover,
}: {
  vm: CognitionTraceVM;
  onHover: (key: string | null) => void;
}) {
  return (
    <div data-screen-label="Cognition disclosure">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>source</TableHead>
            <TableHead>result</TableHead>
            <TableHead>reason</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {vm.disclosures.map((row) => (
            <TableRow key={row.key}>
              <TableCell>
                <TraceTagChip label={row.sourceLabel} sourceKey={row.sourceKey} onHover={onHover} />
              </TableCell>
              <TableCell>
                <Badge variant={row.allowed ? "outline" : "destructive"}>
                  {row.allowed ? "disclosed" : "blocked"}
                </Badge>
              </TableCell>
              <TableCell>
                {row.reasons.length > 1 ? (
                  <HoverCard>
                    <HoverCardTrigger className="font-mono text-xs">{row.reason}</HoverCardTrigger>
                    <HoverCardContent className="font-mono whitespace-pre-line text-xs">
                      {row.reasons.join("\n")}
                    </HoverCardContent>
                  </HoverCard>
                ) : (
                  <span className="font-mono" style={{ fontSize: 9 }}>
                    {row.reason}
                  </span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {!vm.disclosures.length && <EmptyRow />}
    </div>
  );
}

function ExposureTab({ vm, onPayload }: { vm: CognitionTraceVM; onPayload: (title: string, payload: string) => void }) {
  return (
    <div data-screen-label="Cognition prompt exposure">
      {vm.exposures.map((row) => (
        <Collapsible key={row.key}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 4px",
                border: 0,
                borderTop: "1px solid hsl(var(--border))",
                background: "transparent",
                color: "hsl(var(--foreground))",
                textAlign: "left",
              }}
            >
              <Badge variant="outline">{row.kind}</Badge>
              <span className="font-mono" style={{ fontSize: 9 }}>
                {row.label}
              </span>
              <span
                className="font-mono"
                style={{ marginLeft: "auto", fontSize: 8, color: "hsl(var(--muted-foreground))" }}
              >
                {row.meta}
              </span>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div style={{ padding: "0 4px 10px", display: "grid", gap: 6 }}>
              <span style={{ fontSize: 10 }}>{row.preview}</span>
              <ScrollArea style={{ height: 110 }}>
                <pre className="font-mono" style={{ fontSize: 8.5, whiteSpace: "pre-wrap" }}>
                  {row.payload}
                </pre>
              </ScrollArea>
              <Button variant="outline" size="sm" onClick={() => onPayload(row.label, row.payload)}>
                payload
              </Button>
            </div>
          </CollapsibleContent>
        </Collapsible>
      ))}
      {!vm.exposures.length && <EmptyRow />}
    </div>
  );
}

function JobsTab({ vm }: { vm: CognitionTraceVM }) {
  return (
    <div data-screen-label="Cognition jobs" style={{ display: "grid", gap: 10 }}>
      {vm.jobs.map((job) => (
        <div key={job.key} style={{ border: "1px solid hsl(var(--border))", padding: 9 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="font-mono" style={{ fontSize: 9 }}>
              {job.id}
            </span>
            <Badge variant={job.state === "failed" || job.state === "stale_rejected" ? "destructive" : "outline"}>
              {job.state}
            </Badge>
            <span className="font-mono" style={{ fontSize: 8.5, marginLeft: "auto" }}>
              attempts {job.attempts}
            </span>
          </div>
          <div className="font-mono" style={{ fontSize: 8, marginTop: 5, color: "hsl(var(--muted-foreground))" }}>
            {job.timeline}
          </div>
          <div className="font-mono" style={{ fontSize: 8, marginTop: 3 }}>
            lease {job.lease} · generation {job.generations}
          </div>
          {job.error && (
            <div className="font-mono" style={{ fontSize: 8.5, color: "hsl(var(--destructive))", marginTop: 4 }}>
              {job.error}
            </div>
          )}
        </div>
      ))}
      {!vm.jobs.length && <EmptyRow />}
      <span className="font-mono" style={SECTION_LABEL}>
        Effective config
      </span>
      {vm.config.map((section) => (
        <div key={section.section} style={{ borderTop: "1px solid hsl(var(--border))", paddingTop: 6 }}>
          <span className="font-mono" style={SECTION_LABEL}>
            {section.section}
          </span>
          {section.values.map((row) => (
            <div key={row.key} className="font-mono" style={{ display: "flex", gap: 12, fontSize: 8.5 }}>
              <span style={{ color: "hsl(var(--muted-foreground))" }}>{row.key}</span>
              <span style={{ marginLeft: "auto", textAlign: "right" }}>{row.value}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function CanonicalTruth({ vm }: { vm: CognitionTraceVM }) {
  return (
    <Card style={{ borderStyle: "dashed", borderColor: "hsl(var(--destructive) / 0.65)" }}>
      <Collapsible>
        <CardHeader style={{ padding: 10 }}>
          <CollapsibleTrigger asChild>
            <Button variant="outline" size="sm" className="font-mono tracking-widest uppercase">
              canonical_truth
            </Button>
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent style={{ padding: "0 10px 10px", display: "grid", gap: 8 }}>
            {[
              ...vm.canonical.events,
              ...vm.canonical.siblings,
              ...vm.canonical.secrets,
            ].map((row) => (
              <div key={row.key} style={{ borderTop: "1px solid hsl(var(--border))", paddingTop: 6 }}>
                <div className="font-mono" style={{ fontSize: 8.5, color: "hsl(var(--destructive))" }}>
                  {row.label}
                </div>
                <div style={{ fontSize: 10 }}>{row.summary}</div>
                <pre className="font-mono" style={{ fontSize: 8, whiteSpace: "pre-wrap" }}>
                  {row.payload}
                </pre>
              </div>
            ))}
            {!vm.canonical.events.length &&
              !vm.canonical.siblings.length &&
              !vm.canonical.secrets.length && <EmptyRow />}
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

export default function CognitionTrace({
  open,
  onOpenChange,
  vm,
  loading,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  vm: CognitionTraceVM | null;
  loading: boolean;
  error: string | null;
}) {
  const [activeSource, setActiveSource] = useState<string | null>(null);
  const [payloadDialog, setPayloadDialog] = useState<{ title: string; payload: string } | null>(null);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-screen-label="Character cognition inspector"
        style={{ width: "min(1040px, 94vw)", maxWidth: "none", height: "88vh", display: "flex", flexDirection: "column" }}
      >
        <DialogHeader>
          <DialogTitle className="font-mono" style={{ fontSize: 13 }}>
            {vm?.title ?? "Character cognition"}
          </DialogTitle>
          {vm && (
            <div className="font-mono" style={{ fontSize: 8.5, color: "hsl(var(--muted-foreground))" }}>
              {vm.anchor} · {vm.timeline}
            </div>
          )}
        </DialogHeader>
        {loading && (
          <div style={{ display: "grid", gap: 10 }}>
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        )}
        {error && <div className="font-mono text-destructive text-sm">{error}</div>}
        {vm && !loading && !error && (
          <ScrollArea style={{ flex: 1, minHeight: 0 }}>
            <Card>
              <CardContent style={{ padding: 10 }}>
                <Tabs defaultValue="accounts">
                  <TabsList className="grid w-full grid-cols-5">
                    <TabsTrigger value="accounts">accounts</TabsTrigger>
                    <TabsTrigger value="recall">recall</TabsTrigger>
                    <TabsTrigger value="disclosure">disclosure</TabsTrigger>
                    <TabsTrigger value="exposure">exposure</TabsTrigger>
                    <TabsTrigger value="jobs">jobs</TabsTrigger>
                  </TabsList>
                  <TabsContent value="accounts">
                    <AccountsTab vm={vm} activeSource={activeSource} />
                  </TabsContent>
                  <TabsContent value="recall">
                    <RecallTab vm={vm} onHover={setActiveSource} />
                  </TabsContent>
                  <TabsContent value="disclosure">
                    <DisclosureTab vm={vm} onHover={setActiveSource} />
                  </TabsContent>
                  <TabsContent value="exposure">
                    <ExposureTab
                      vm={vm}
                      onPayload={(title, payload) => setPayloadDialog({ title, payload })}
                    />
                  </TabsContent>
                  <TabsContent value="jobs">
                    <JobsTab vm={vm} />
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
            <div style={{ height: 10 }} />
            <CanonicalTruth vm={vm} />
          </ScrollArea>
        )}
      </DialogContent>
      <Dialog open={payloadDialog != null} onOpenChange={(next) => !next && setPayloadDialog(null)}>
        <DialogContent style={{ maxWidth: 760 }}>
          <DialogHeader>
            <DialogTitle className="font-mono">{payloadDialog?.title}</DialogTitle>
          </DialogHeader>
          <ScrollArea style={{ height: "60vh" }}>
            <pre className="font-mono" style={{ fontSize: 9, whiteSpace: "pre-wrap" }}>
              {payloadDialog?.payload}
            </pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
