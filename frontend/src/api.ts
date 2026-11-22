import type { CreatedProject, Project, Readiness } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getReadiness(): Promise<Readiness> {
  return request<Readiness>("/ready");
}

export function createProject(input: {
  brief: string;
  constraints: Record<string, string>;
  interactive: boolean;
}): Promise<CreatedProject> {
  return request<CreatedProject>("/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

export function cancelProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}/cancel`, { method: "POST" });
}

export function answerProject(projectId: string, answer: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/projects/${projectId}/answers`, {
    method: "POST",
    body: JSON.stringify({ answer }),
  });
}

export function artifactUrl(projectId: string, path: string): string {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return `/projects/${projectId}/artifacts/${encodedPath}`;
}
