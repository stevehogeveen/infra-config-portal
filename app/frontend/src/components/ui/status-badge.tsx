import { cn } from "../../lib/utils";

export type StatusBadgeStatus =
  | "ready"
  | "blocked"
  | "offline"
  | "not-configured"
  | "needs-attention"
  | "safe-to-run"
  | "plan-only";

type StatusBadgeProps = {
  status: StatusBadgeStatus;
  label?: string;
  className?: string;
};

const statusLabels: Record<StatusBadgeStatus, string> = {
  ready: "Ready",
  blocked: "Blocked",
  offline: "Offline",
  "not-configured": "Not configured",
  "needs-attention": "Needs attention",
  "safe-to-run": "Safe to run",
  "plan-only": "Plan only"
};

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  return (
    <span className={cn("ui-status-badge", `ui-status-badge-${status}`, className)}>
      {label ?? statusLabels[status]}
    </span>
  );
}
