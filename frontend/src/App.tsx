import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  answerProject,
  artifactUrl,
  cancelProject,
  createProject,
  getProject,
  getReadiness,
} from "./api";
import {
  DELIVERY_PHASES,
  formatBytes,
  phaseIndex,
  phaseLabel,
  projectProgress,
} from "./progress";
import type { Project, ProjectEvent, Readiness } from "./types";

const STORAGE_KEY = "foundry.recent-projects";
const EVENT_TYPES = [
  "queued",
  "started",
  "phase",
  "agent",
  "artifact",
  "heartbeat",
  "answer",
  "result",
  "completed",
  "failed",
  "cancelled",
];
const TERMINAL_EVENT_TYPES = new Set(["completed", "failed", "cancelled"]);

type StreamState = "connecting" | "live" | "reconnecting" | "closed";

const STARTERS = [
  "A customer support inbox with team assignments and SLA tracking",
  "An expense tracker for freelancers with receipt uploads and reports",
  "A lightweight incident response dashboard with a shared timeline",
];

function loadRecentIds(): string[] {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(stored) ? stored.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function saveRecentId(projectId: string): void {
  const next = [projectId, ...loadRecentIds().filter((item) => item !== projectId)].slice(0, 8);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

function shortId(projectId: string): string {
  return projectId.slice(0, 7).toUpperCase();
}

function relativeTime(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function streamLabel(state: StreamState): string {
  if (state === "live") return "Stream connected";
  if (state === "reconnecting") return "Reconnecting";
  if (state === "closed") return "Stream ended";
  return "Connecting";
}

function activityIcon(type: string): string {
  if (type === "completed") return "check";
  if (type === "failed" || type === "cancelled") return "close";
  if (type === "artifact") return "file";
  if (type === "agent") return "spark";
  return "pulse";
}

function activityDetail(event: ProjectEvent): string | null {
  if (event.type === "artifact") {
    const count = event.data.artifact_count;
    return typeof count === "number" ? `${count} project files available` : null;
  }
  if (event.type === "heartbeat") {
    const elapsed = event.data.elapsed_seconds;
    return typeof elapsed === "number" ? `Worker active for ${elapsed}s` : "Worker is responsive";
  }
  if (event.type === "agent" && typeof event.data.state === "string") {
    return event.data.state === "thinking" ? "Model reasoning" : `Tool ${event.data.state}`;
  }
  return null;
}

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    plus: <path d="M12 5v14M5 12h14" />,
    spark: <path d="m12 3 1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4L12 3Zm6 12 .7 2.3L21 18l-2.3.7L18 21l-.7-2.3L15 18l2.3-.7L18 15Z" />,
    layers: <path d="m12 3 9 5-9 5-9-5 9-5Zm-7.5 9 7.5 4 7.5-4M4.5 16l7.5 4 7.5-4" />,
    file: <path d="M6 2h8l4 4v16H6V2Zm8 0v5h5M9 12h6M9 16h6" />,
    pulse: <path d="M3 12h4l2-6 4 12 2-6h6" />,
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    arrow: <path d="M5 12h14M14 7l5 5-5 5" />,
    download: <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14" />,
    stop: <path d="M7 7h10v10H7z" />,
    message: <path d="M4 5h16v12H8l-4 4V5Z" />,
    terminal: <path d="m5 7 4 5-4 5m7 0h7" />,
  };
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

function StatusPill({ project }: { project: Project }) {
  const label = project.status === "running" ? "Agents working" : project.status;
  return (
    <span className={`status-pill status-${project.status}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}

function Sidebar({
  projects,
  activeId,
  onSelect,
  onNew,
}: {
  projects: Project[];
  activeId: string | null;
  onSelect: (project: Project) => void;
  onNew: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><span /><span /><span /></div>
        <div><strong>Foundry</strong><small>Agentic SDLC</small></div>
      </div>
      <button className="new-project-button" onClick={onNew} type="button">
        <Icon name="plus" /> New project
      </button>
      <nav className="side-nav" aria-label="Workspace">
        <p className="nav-label">Workspace</p>
        <button className={!activeId ? "nav-item active" : "nav-item"} onClick={onNew} type="button">
          <Icon name="spark" /> Product brief
        </button>
        <div className="nav-item muted"><Icon name="layers" /> Agent team <span>6</span></div>
      </nav>
      <div className="recent-projects">
        <p className="nav-label">Recent runs</p>
        {projects.length === 0 ? (
          <p className="empty-recent">Your launched projects will appear here.</p>
        ) : projects.map((project) => (
          <button
            key={project.project_id}
            className={`recent-item ${activeId === project.project_id ? "active" : ""}`}
            onClick={() => onSelect(project)}
            type="button"
          >
            <span className={`recent-indicator status-${project.status}`} />
            <span><strong>{project.brief.text.slice(0, 36)}</strong><small>{phaseLabel(project.phase)}</small></span>
          </button>
        ))}
      </div>
      <div className="sidebar-footer">
        <span className="avatar">AI</span>
        <div><strong>Engineering team</strong><small>6 specialists online</small></div>
        <span className="online-dot" />
      </div>
    </aside>
  );
}

function BriefComposer({
  readiness,
  onCreated,
}: {
  readiness: Readiness | null;
  onCreated: (project: Project) => void;
}) {
  const [brief, setBrief] = useState("");
  const [stack, setStack] = useState("");
  const [audience, setAudience] = useState("");
  const [interactive, setInteractive] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!brief.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const constraints = Object.fromEntries(
        Object.entries({ stack: stack.trim(), target_users: audience.trim() }).filter(([, value]) => value),
      );
      const created = await createProject({ brief: brief.trim(), constraints, interactive });
      saveRecentId(created.project_id);
      const project = await getProject(created.project_id);
      onCreated(project);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the project");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="brief-page">
      <section className="brief-hero">
        <span className="eyebrow"><Icon name="spark" size={15} /> AI product engineering</span>
        <h1>Turn an idea into<br /><em>working software.</em></h1>
        <p>Describe what you want to build. A coordinated team of AI specialists will plan, architect, implement, test, and package it.</p>
      </section>

      {readiness && !readiness.ready && (
        <div className="readiness-banner" role="status">
          <span><Icon name="terminal" /></span>
          <div><strong>Runtime setup needed</strong><p>{readiness.issues[0]}</p></div>
        </div>
      )}

      <form className="brief-card" onSubmit={submit}>
        <div className="brief-card-heading">
          <div><span>01</span><div><h2>What are we building?</h2><p>Explain the problem, users, and the outcome you need.</p></div></div>
          <span className="optional-badge">Natural language</span>
        </div>
        <div className="textarea-shell">
          <textarea
            aria-label="Product brief"
            maxLength={20000}
            onChange={(event) => setBrief(event.target.value)}
            placeholder="For example: Build a collaborative expense tracker for small teams. Users should be able to upload receipts, categorize expenses, invite teammates, and export monthly reports..."
            required
            rows={7}
            value={brief}
          />
          <span className="character-count">{brief.length.toLocaleString()} / 20,000</span>
        </div>
        <div className="starter-row">
          <span>Try a starting point</span>
          <div>{STARTERS.map((starter, index) => <button key={starter} onClick={() => setBrief(starter)} type="button">0{index + 1}</button>)}</div>
        </div>
        <div className="constraint-grid">
          <label><span>Preferred stack <small>optional</small></span><input onChange={(event) => setStack(event.target.value)} placeholder="e.g. React + FastAPI" value={stack} /></label>
          <label><span>Target users <small>optional</small></span><input onChange={(event) => setAudience(event.target.value)} placeholder="e.g. Operations teams" value={audience} /></label>
        </div>
        <div className="brief-footer">
          <label className="toggle-row">
            <input checked={interactive} onChange={(event) => setInteractive(event.target.checked)} type="checkbox" />
            <span className="toggle" aria-hidden="true" />
            <span><strong>Allow clarifying questions</strong><small>The PM may pause to ask for direction.</small></span>
          </label>
          <button className="launch-button" disabled={submitting || !brief.trim()} type="submit">
            {submitting ? <span className="spinner" /> : <Icon name="spark" />}
            {submitting ? "Starting team…" : "Start building"}
          </button>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
      </form>

      <div className="team-strip">
        <span>YOUR AI TEAM</span>
        {[
          ["PM", "Product manager"], ["AR", "Architect"], ["BE", "Engineer"],
          ["UI", "UI developer"], ["QA", "QA tester"], ["RV", "Reviewer"],
        ].map(([code, name]) => <div key={code}><i>{code}</i><span>{name}</span></div>)}
      </div>
    </div>
  );
}

function PhaseRail({ project }: { project: Project }) {
  const current = phaseIndex(project.phase);
  return (
    <ol className="phase-rail">
      {DELIVERY_PHASES.map((item, index) => {
        const state = index < current || project.status === "completed" ? "done" : index === current ? "current" : "future";
        return (
          <li className={state} key={item.phase}>
            <span className="phase-node">{state === "done" ? <Icon name="check" size={13} /> : index + 1}</span>
            <span><strong>{item.short}</strong><small>{state === "done" ? "Complete" : state === "current" ? "In progress" : "Pending"}</small></span>
          </li>
        );
      })}
    </ol>
  );
}

function ProjectDashboard({
  project,
  events,
  streamState,
  onCancel,
  onAnswer,
}: {
  project: Project;
  events: ProjectEvent[];
  streamState: StreamState;
  onCancel: () => Promise<void>;
  onAnswer: (answer: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");
  const [answering, setAnswering] = useState(false);
  const [, setClock] = useState(0);
  const progress = projectProgress(project.phase, project.status);
  const running = project.status === "running" || project.status === "queued";
  const lastEvent = events.at(-1);

  useEffect(() => {
    const timer = window.setInterval(() => setClock((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  async function submitAnswer(event: FormEvent) {
    event.preventDefault();
    if (!answer.trim()) return;
    setAnswering(true);
    try {
      await onAnswer(answer.trim());
      setAnswer("");
    } finally {
      setAnswering(false);
    }
  }

  return (
    <div className="project-page">
      <header className="project-heading">
        <div>
          <span className="project-kicker">RUN / {shortId(project.project_id)}</span>
          <h1>{project.brief.text.split(/[.!?]/)[0]}</h1>
          <p>Created {relativeTime(project.created_at)} · Workspace <code>{project.workspace}</code></p>
        </div>
        <div className="project-actions">
          <StatusPill project={project} />
          {running && <button className="cancel-button" onClick={() => void onCancel()} type="button"><Icon name="stop" size={15} /> Stop run</button>}
        </div>
      </header>

      <section className="progress-card">
        <div className="progress-copy">
          <div><span className="pulse-icon"><Icon name="pulse" /></span><div><small>Current phase</small><strong>{phaseLabel(project.phase)}</strong></div></div>
          <span className="progress-value">{progress}<small>%</small></span>
        </div>
        <div className="progress-track" aria-label={`${progress}% complete`} role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="progress-meta"><span>{project.status === "completed" ? "Delivery complete" : "The team is working autonomously"}</span><span>{project.artifacts.length} files detected</span></div>
      </section>

      <div className="dashboard-grid">
        <section className="panel phase-panel">
          <div className="panel-heading"><div><span className="panel-icon"><Icon name="layers" /></span><div><h2>Delivery pipeline</h2><p>Every gate must pass before the next phase.</p></div></div></div>
          <PhaseRail project={project} />
        </section>

        <section className="panel activity-panel">
          <div className="panel-heading"><div><span className="panel-icon"><Icon name="pulse" /></span><div><h2>Live activity</h2><p>Agent actions, file changes, and worker heartbeats.</p></div></div><span className={streamState === "live" ? "live-badge" : "live-badge idle"}>{streamState === "live" ? "LIVE" : streamState.toUpperCase()}</span></div>
          <div className="activity-health">
            <span className={`connection-state connection-${streamState}`} />
            <strong>{streamLabel(streamState)}</strong>
            <span>{lastEvent ? `Last signal ${relativeTime(lastEvent.timestamp)}` : "Waiting for first signal"}</span>
            <span>{project.artifacts.length} files</span>
          </div>
          <div className="activity-list" aria-live="polite">
            {events.length === 0 ? <div className="activity-empty"><span className="spinner dark" /><p>Connecting to the project stream…</p></div> : events.slice().reverse().map((event) => (
              <div className={`activity-item event-${event.type}`} key={event.sequence}>
                <span><Icon name={activityIcon(event.type)} size={14} /></span>
                <div>
                  <strong>{event.message}</strong>
                  {activityDetail(event) && <p>{activityDetail(event)}</p>}
                  <small>{new Date(event.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })} · {event.type}</small>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel artifacts-panel">
          <div className="panel-heading"><div><span className="panel-icon"><Icon name="file" /></span><div><h2>Generated files</h2><p>Continuously refreshed from the project workspace.</p></div></div><span className="count-badge">{project.artifacts.length}</span></div>
          {project.artifacts.length === 0 ? (
            <div className="files-empty"><Icon name="file" size={28} /><strong>No files yet</strong><p>Artifacts will appear as the engineering team creates them.</p></div>
          ) : (
            <div className="file-list">{project.artifacts.map((artifact) => (
              <a href={artifactUrl(project.project_id, artifact.path)} key={artifact.path} target="_blank" rel="noreferrer">
                <span className="file-type">{artifact.path.split(".").pop()?.slice(0, 4).toUpperCase() ?? "FILE"}</span>
                <span><strong>{artifact.path.split("/").pop()}</strong><small>{artifact.path.includes("/") ? artifact.path.slice(0, artifact.path.lastIndexOf("/")) : "project root"}</small></span>
                <small>{formatBytes(artifact.size)}</small><Icon name="download" size={16} />
              </a>
            ))}</div>
          )}
        </section>

        <section className="panel direction-panel">
          <div className="panel-heading"><div><span className="panel-icon"><Icon name="message" /></span><div><h2>Add direction</h2><p>Send a clarification while the run is active.</p></div></div></div>
          {running ? (
            <form onSubmit={submitAnswer}><textarea aria-label="Clarification answer" onChange={(event) => setAnswer(event.target.value)} placeholder="For example: prioritize the admin workflow first…" rows={3} value={answer} /><button disabled={!answer.trim() || answering} type="submit"><Icon name="message" size={15} />{answering ? "Sending…" : "Send to PM"}</button></form>
          ) : <div className="run-ended"><Icon name="check" /><p>This run has ended. Start a new project to make further changes.</p></div>}
        </section>
      </div>

      {project.error && <div className="error-panel" role="alert"><Icon name="close" /><div><strong>The run stopped with an error</strong><p>{project.error}</p></div></div>}
    </div>
  );
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project | null>(null);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [streamState, setStreamState] = useState<StreamState>("closed");

  const refreshProject = useCallback(async (projectId: string) => {
    const project = await getProject(projectId);
    setSelected((current) => current?.project_id === projectId ? project : current);
    setProjects((current) => [project, ...current.filter((item) => item.project_id !== projectId)]);
    return project;
  }, []);

  useEffect(() => {
    void getReadiness().then(setReadiness).catch(() => setReadiness(null));
    const ids = loadRecentIds();
    void Promise.all(ids.map((id) => getProject(id).catch(() => null))).then((items) => {
      setProjects(items.filter((item): item is Project => item !== null));
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    setEvents([]);
    setStreamState("connecting");
    const source = new EventSource(`/projects/${selected.project_id}/events`);
    source.onopen = () => setStreamState("live");
    source.onerror = () => setStreamState("reconnecting");
    const receive = (raw: Event) => {
      const event = raw as MessageEvent<string>;
      try {
        const parsed = JSON.parse(event.data) as ProjectEvent;
        setEvents((current) => current.some((item) => item.sequence === parsed.sequence) ? current : [...current, parsed].slice(-250));
        void refreshProject(selected.project_id);
        if (TERMINAL_EVENT_TYPES.has(parsed.type)) {
          source.close();
          setStreamState("closed");
        }
      } catch {
        // A malformed event should not disconnect later valid progress updates.
      }
    };
    EVENT_TYPES.forEach((type) => source.addEventListener(type, receive));
    return () => {
      source.close();
      setStreamState("closed");
    };
  }, [refreshProject, selected?.project_id]);

  useEffect(() => {
    if (!selected || ["completed", "failed", "cancelled"].includes(selected.status)) return;
    const projectId = selected.project_id;
    const timer = window.setInterval(() => {
      void refreshProject(projectId).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [refreshProject, selected?.project_id, selected?.status]);

  const activeId = selected?.project_id ?? null;
  const pageTitle = useMemo(() => selected ? `${phaseLabel(selected.phase)} · Foundry` : "Foundry · Agentic SDLC", [selected]);
  useEffect(() => { document.title = pageTitle; }, [pageTitle]);

  function selectProject(project: Project) {
    setSelected(project);
    saveRecentId(project.project_id);
  }

  async function cancel() {
    if (!selected) return;
    const project = await cancelProject(selected.project_id);
    setSelected(project);
    setProjects((current) => [project, ...current.filter((item) => item.project_id !== project.project_id)]);
  }

  async function answer(answerText: string) {
    if (!selected) return;
    await answerProject(selected.project_id, answerText);
  }

  return (
    <div className="app-shell">
      <Sidebar projects={projects} activeId={activeId} onSelect={selectProject} onNew={() => setSelected(null)} />
      <main>
        <div className="topbar">
          <div className="mobile-brand"><span className="brand-mark"><span /><span /><span /></span><strong>Foundry</strong></div>
          <div className="system-state"><span className={readiness?.ready ? "online-dot" : "warning-dot"} /> {readiness?.ready ? "Runtime ready" : "API connected"}</div>
          <a href="/docs" target="_blank" rel="noreferrer">API docs</a>
        </div>
        {selected ? (
          <ProjectDashboard project={selected} events={events} streamState={streamState} onCancel={cancel} onAnswer={answer} />
        ) : (
          <BriefComposer readiness={readiness} onCreated={selectProject} />
        )}
      </main>
    </div>
  );
}
