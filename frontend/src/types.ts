export type Phase =
  | "INTAKE"
  | "PRD"
  | "ARCHITECTURE"
  | "PLANNING"
  | "BOOTSTRAP"
  | "BUILDING"
  | "INTEGRATION_QA"
  | "HARDENING"
  | "RELEASE_READY"
  | "READY_FOR_HUMAN"
  | "SHIPPED"
  | "NEEDS_HUMAN"
  | "FAILED";

export type ProjectStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface Brief {
  text: string;
  constraints: Record<string, string>;
  interactive: boolean;
}

export interface Artifact {
  path: string;
  size: number;
}

export interface Project {
  project_id: string;
  status: ProjectStatus;
  phase: Phase;
  brief: Brief;
  workspace: string;
  artifacts: Artifact[];
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreatedProject {
  project_id: string;
  status: ProjectStatus;
  phase: Phase;
  workspace: string;
}

export interface ProjectEvent {
  sequence: number;
  type: string;
  message: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface Readiness {
  ready: boolean;
  issues: string[];
  deepagents_version: string | null;
  execution: string;
}
