import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  FileDown,
  Play,
  RotateCcw,
  ShieldCheck,
  X
} from "lucide-react";

import type { LabBuildPlan, LabBuildRun, LabBuildStep } from "../../types";

export function LabBuildJourney({
  error,
  loading,
  onClose,
  onOpenDetails,
  onRefresh,
  onReload,
  onResume,
  onRetry,
  onStart,
  plan,
  run
}: {
  error?: string;
  loading?: boolean;
  onClose: () => void;
  onOpenDetails: () => void;
  onRefresh: () => void;
  onReload: () => void;
  onResume: () => void;
  onRetry: (stepId: string) => void;
  onStart: () => void;
  plan: LabBuildPlan | null;
  run: LabBuildRun | null;
}) {
  const isComplete = run && ["completed", "warning", "failed"].includes(run.status);

  return (
    <section className="lab-build-journey" aria-label="Lab build journey" data-testid="lab-build-journey">
      <header className="lab-build-header">
        <div>
          <p className="operator-kicker">Selected kit</p>
          <strong>{run?.kit_name ?? plan?.kit_name ?? "Current lab"}</strong>
          <span>{run?.deployment_mode ?? plan?.deployment_mode ?? "Build plan"}</span>
        </div>
        <button aria-label="Close build journey" className="icon-button" onClick={onClose} title="Close" type="button">
          <X size={18} />
        </button>
      </header>

      {error && <p className="lab-build-feedback error" role="alert">{error}</p>}
      {!plan && !run ? (
        error && !loading ? (
          <div className="lab-build-actions">
            <button className="lab-build-primary" data-testid="lab-build-primary-action" onClick={onReload} type="button">
              <RotateCcw size={17} /> Retry Loading
            </button>
          </div>
        ) : (
          <div className="lab-build-loading"><Clock3 size={20} /> Loading the build plan...</div>
        )
      ) : isComplete && run ? (
        <CompletionReport loading={loading} onClose={onClose} onOpenDetails={onOpenDetails} onRetry={onRetry} run={run} />
      ) : run ? (
        <RunConsole
          loading={loading}
          onOpenDetails={onOpenDetails}
          onRefresh={onRefresh}
          onResume={onResume}
          run={run}
        />
      ) : plan ? (
        <BuildPlan loading={loading} onStart={onStart} plan={plan} />
      ) : null}
    </section>
  );
}

function BuildPlan({ loading, onStart, plan }: { loading?: boolean; onStart: () => void; plan: LabBuildPlan }) {
  return (
    <div className="lab-build-plan" aria-label="Build Plan">
      <div className="lab-build-intro-row">
        <div className="lab-build-intro">
          <p className="operator-kicker">Build Plan</p>
          <h1>{plan.headline}</h1>
          <p>{plan.supporting_message}</p>
        </div>
        <button
          className="lab-build-primary"
          data-testid="lab-build-primary-action"
          disabled={loading || plan.blockers.length > 0}
          onClick={onStart}
          type="button"
        >
          <Play size={17} />
          {loading ? "Starting..." : plan.primary_action}
        </button>
      </div>

      {plan.blockers.length > 0 && (
        <div className="lab-build-blocker" role="alert">
          <AlertTriangle size={18} />
          <div>
            <strong>Resolve before starting</strong>
            <p>{plan.blockers[0]}</p>
          </div>
        </div>
      )}

      <ol className="lab-build-hallway" aria-label="Ordered build steps">
        {plan.steps.map((step) => (
          <li key={step.step_id}>
            <StepMarker status={step.status} />
            <div>
              <span>Step {step.order}</span>
              <strong>{step.label}</strong>
              <p>{step.description}</p>
              {step.rationale && <small>{step.rationale}</small>}
              {!isSafeAutomaticStep(step) && <small className="lab-build-pause">Pauses for your approval</small>}
            </div>
          </li>
        ))}
      </ol>

    </div>
  );
}

function RunConsole({
  loading,
  onOpenDetails,
  onRefresh,
  onResume,
  run
}: {
  loading?: boolean;
  onOpenDetails: () => void;
  onRefresh: () => void;
  onResume: () => void;
  run: LabBuildRun;
}) {
  const current = currentStep(run);
  const isRunning = run.status === "running";
  const isGuardedWait = run.status === "waiting" && current && !isSafeAutomaticStep(current);
  const actionLabel = isRunning ? "Refresh Status" : isGuardedWait ? "Continue Build" : "Resume Build";
  const action = isRunning ? onRefresh : onResume;

  return (
    <div className="lab-run-console" aria-label="Run Console">
      <div className="lab-build-intro">
        <p className="operator-kicker">Run Console</p>
        <h1>{run.headline}</h1>
        <p>{run.operator_message}</p>
      </div>

      <div className="lab-run-progress">
        <div>
          <strong>{current ? `Step ${current.order} of ${run.progress.total}` : "Build in progress"}</strong>
          <span>{elapsedLabel(run.started_at, run.finished_at)}</span>
        </div>
        <progress aria-label="Build progress" max={run.progress.total} value={run.progress.completed} />
        <small>{run.progress.percent}% complete</small>
      </div>

      {current && (
        <article className={`lab-run-current ${current.status}`}>
          <StepMarker status={current.status} />
          <div>
            <span>{statusLabel(current.status)}</span>
            <h2>{current.label}</h2>
            <p>{current.operator_message}</p>
            <small>{current.suggested_action}</small>
          </div>
        </article>
      )}

      <TechnicalLog run={run} />

      <div className="lab-build-actions">
        <button className="lab-build-primary" data-testid="lab-build-primary-action" disabled={loading} onClick={action} type="button">
          {isRunning ? <RotateCcw size={17} /> : isGuardedWait ? <ShieldCheck size={17} /> : <Play size={17} />}
          {loading ? "Checking..." : actionLabel}
        </button>
        {isGuardedWait && (
          <button className="lab-build-secondary" onClick={onOpenDetails} type="button">
            Open Details
          </button>
        )}
      </div>
    </div>
  );
}

function CompletionReport({
  loading,
  onClose,
  onOpenDetails,
  onRetry,
  run
}: {
  loading?: boolean;
  onClose: () => void;
  onOpenDetails: () => void;
  onRetry: (stepId: string) => void;
  run: LabBuildRun;
}) {
  const exceptions = run.steps.filter((step) => ["failed", "blocked", "warning"].includes(step.status));
  const retryable = exceptions.find((step) => step.can_retry);
  const primaryLabel = retryable ? "Retry Check" : run.status === "failed" ? "Open Details" : "Back to Operator Home";
  const primaryAction = retryable ? () => onRetry(retryable.step_id) : run.status === "failed" ? onOpenDetails : onClose;

  return (
    <div className="lab-completion-report" aria-label="Completion Report">
      <div className="lab-build-intro">
        <p className="operator-kicker">Completion Report</p>
        <h1>{run.headline}</h1>
        <p>{run.operator_message}</p>
      </div>

      <dl className="lab-completion-counts" aria-label="Build result counts">
        <div><dt>Completed</dt><dd>{run.counts.completed}</dd></div>
        <div><dt>Warnings</dt><dd>{run.counts.warnings}</dd></div>
        <div><dt>Failed</dt><dd>{run.counts.failed}</dd></div>
      </dl>

      {exceptions.length > 0 ? (
        <div className="lab-completion-exceptions">
          {exceptions.map((step) => (
            <article key={step.step_id}>
              <StepMarker status={step.status} />
              <div>
                <strong>{step.label}</strong>
                <p>{step.operator_message}</p>
                <small>{step.suggested_action}</small>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="lab-completion-clear"><CheckCircle2 size={20} /> Every required step completed.</div>
      )}

      <TechnicalLog run={run} />

      <div className="lab-build-actions">
        <button className="lab-build-primary" data-testid="lab-build-primary-action" disabled={loading} onClick={primaryAction} type="button">
          {retryable ? <RotateCcw size={17} /> : <CheckCircle2 size={17} />}
          {loading ? "Checking..." : primaryLabel}
        </button>
        <button className="lab-build-secondary" onClick={() => exportRunSummary(run)} type="button">
          <FileDown size={16} /> Export Summary
        </button>
      </div>
    </div>
  );
}

function TechnicalLog({ run }: { run: LabBuildRun }) {
  const technical = run.steps
    .filter((step) => step.technical_details)
    .map((step) => `${step.order}. ${step.label}\n${step.technical_details}`)
    .join("\n\n");

  return (
    <details className="lab-build-advanced">
      <summary>Advanced</summary>
      <div>
        <p>Dependency and technical evidence for this run.</p>
        <pre aria-label="Technical build log">{technical || "No technical evidence has been recorded yet."}</pre>
      </div>
    </details>
  );
}

function StepMarker({ status }: { status: string }) {
  if (["succeeded", "skipped"].includes(status)) return <CheckCircle2 aria-hidden="true" size={20} />;
  if (["failed", "blocked", "warning"].includes(status)) return <AlertTriangle aria-hidden="true" size={20} />;
  if (["preflight", "running", "waiting"].includes(status)) return <Clock3 aria-hidden="true" size={20} />;
  return <Circle aria-hidden="true" size={20} />;
}

function currentStep(run: LabBuildRun): LabBuildStep | null {
  return run.steps.find((step) => step.step_id === run.current_step_id) ?? null;
}

function isSafeAutomaticStep(step: LabBuildStep) {
  return ["read_only", "report_only"].includes(step.action_mode);
}

function statusLabel(status: string) {
  return status.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function elapsedLabel(startedAt: string, finishedAt: string | null) {
  const started = new Date(startedAt).getTime();
  const finished = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((finished - started) / 1000));
  if (seconds < 60) return `${seconds}s elapsed`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed`;
}

function exportRunSummary(run: LabBuildRun) {
  const lines = [
    `# Lab Build Report: ${run.kit_name}`,
    "",
    `Status: ${run.status}`,
    `Started: ${run.started_at}`,
    `Finished: ${run.finished_at ?? "Not finished"}`,
    "",
    ...run.steps.flatMap((step) => [
      `## ${step.order}. ${step.label}`,
      `Status: ${step.status}`,
      `Result: ${step.operator_message}`,
      `Next: ${step.suggested_action}`,
      ""
    ])
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `lab-build-${run.run_id.replace(/[^a-z0-9]+/gi, "-")}.md`;
  link.click();
  URL.revokeObjectURL(url);
}
