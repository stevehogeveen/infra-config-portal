import { cn } from "../../lib/utils";
import { ActionLink } from "./action-link";

type BlockerItemProps = {
  severity: "critical" | "warning";
  code: string;
  message: string;
  actionLabel?: string;
  actionHref?: string;
  className?: string;
};

export function BlockerItem({
  severity,
  code,
  message,
  actionLabel,
  actionHref,
  className
}: BlockerItemProps) {
  return (
    <article className={cn("ui-blocker-item", `ui-blocker-item-${severity}`, className)}>
      <div className="ui-blocker-code">{code}</div>
      <p>{message}</p>
      {actionLabel && actionHref && (
        <ActionLink href={actionHref} className="ui-blocker-action">
          {actionLabel}
        </ActionLink>
      )}
    </article>
  );
}
