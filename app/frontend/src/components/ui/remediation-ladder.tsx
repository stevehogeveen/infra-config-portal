import type { ReactNode } from "react";

import { cn } from "../../lib/utils";
import { StatusBadge, type StatusBadgeStatus } from "./status-badge";

export type RemediationStep = {
  detail: string;
  label: string;
  nextAction: string;
  status: StatusBadgeStatus;
};

type RemediationLadderProps = {
  className?: string;
  defaultOpen?: boolean;
  emptyStep?: RemediationStep;
  status: StatusBadgeStatus;
  statusLabel: string;
  steps: RemediationStep[];
  summary: string;
  title: string;
  tone?: "standard" | "optional";
  icon?: ReactNode;
};

export function RemediationLadder({
  className,
  defaultOpen = false,
  emptyStep,
  icon,
  status,
  statusLabel,
  steps,
  summary,
  title,
  tone = "standard"
}: RemediationLadderProps) {
  const visibleSteps = steps.length
    ? steps
    : emptyStep
      ? [emptyStep]
      : [];
  const currentStep = visibleSteps.find((step) => step.status !== "ready") ?? visibleSteps[0];

  return (
    <details className={cn("ui-remediation-ladder", `ui-remediation-ladder-${tone}`, className)} open={defaultOpen}>
      <summary>
        <span className="ui-remediation-title">
          {icon}
          <span>
            <strong>{title}</strong>
            <small>{summary}</small>
          </span>
        </span>
        <StatusBadge label={statusLabel} status={status} />
      </summary>
      {currentStep && (
        <div className="ui-remediation-current">
          <span>Next</span>
          <strong>{currentStep.label}</strong>
          <small>{currentStep.nextAction}</small>
          <StatusBadge status={currentStep.status} />
        </div>
      )}
      <div className="ui-remediation-steps">
        {visibleSteps.map((step) => (
          <div key={`${step.label}-${step.detail}`}>
            <span>{step.label}</span>
            <strong>{step.detail}</strong>
            <small>{step.nextAction}</small>
            <StatusBadge status={step.status} />
          </div>
        ))}
      </div>
    </details>
  );
}
