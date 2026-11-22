import type { Phase, ProjectStatus } from "./types";

export const DELIVERY_PHASES: Array<{ phase: Phase; label: string; short: string }> = [
  { phase: "INTAKE", label: "Product intake", short: "Intake" },
  { phase: "PRD", label: "Requirements", short: "PRD" },
  { phase: "ARCHITECTURE", label: "System design", short: "Architecture" },
  { phase: "PLANNING", label: "Delivery plan", short: "Planning" },
  { phase: "BOOTSTRAP", label: "Project setup", short: "Bootstrap" },
  { phase: "BUILDING", label: "Build iterations", short: "Building" },
  { phase: "INTEGRATION_QA", label: "Integration QA", short: "QA" },
  { phase: "HARDENING", label: "Hardening", short: "Hardening" },
  { phase: "RELEASE_READY", label: "Release review", short: "Release" },
  { phase: "READY_FOR_HUMAN", label: "Human approval", short: "Ready" },
];

const terminalProgress: Partial<Record<Phase, number>> = {
  SHIPPED: 100,
  READY_FOR_HUMAN: 100,
};

export function phaseIndex(phase: Phase): number {
  if (phase === "SHIPPED") return DELIVERY_PHASES.length;
  if (phase === "NEEDS_HUMAN" || phase === "FAILED") return -1;
  return DELIVERY_PHASES.findIndex((item) => item.phase === phase);
}

export function projectProgress(phase: Phase, status: ProjectStatus): number {
  if (status === "completed") return 100;
  if (terminalProgress[phase] !== undefined) return terminalProgress[phase] ?? 100;
  const index = phaseIndex(phase);
  if (index < 0) return 0;
  return Math.max(3, Math.round((index / DELIVERY_PHASES.length) * 100));
}

export function phaseLabel(phase: Phase): string {
  return (
    DELIVERY_PHASES.find((item) => item.phase === phase)?.label ??
    phase.toLowerCase().replaceAll("_", " ")
  );
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
