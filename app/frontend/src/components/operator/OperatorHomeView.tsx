import { AlertTriangle, CheckCircle2, ChevronRight, Eye, Pencil } from "lucide-react";

import type { OperatorHomeModel } from "../../operatorHomeModel";

export function OperatorHomeView({
  detailsOpen,
  error,
  loading,
  model,
  onPrimaryAction,
  onViewDetails
}: {
  detailsOpen: boolean;
  error?: string;
  loading?: boolean;
  model: OperatorHomeModel;
  onPrimaryAction: () => void;
  onViewDetails: () => void;
}) {
  const total = model.Progress.Total;
  const ready = model.Progress.Ready;
  const blocked = model.Progress.Blocked;
  const unchecked = model.Progress.NotChecked;
  const pct = (n: number) => (total > 0 ? `${(n / total) * 100}%` : "0%");
  const stateTone = model.DisplayState === "needs_attention" || model.DisplayState === "not_checked" ? "attention" : model.DisplayState;
  const primaryBusy = loading && model.NextAction.Target === "build";
  const visibleAttentionItems = detailsOpen ? model.AttentionItems : model.AttentionItems.slice(0, 1);
  const hiddenAttentionCount = Math.max(model.AttentionItems.length - visibleAttentionItems.length, 0);

  return (
    <section
      className={`operator-rail operator-rail-${stateTone}`}
      aria-label="Operator Home status and next action"
      data-testid="operator-home"
    >
      <h1 className="operator-rail-eyebrow">Overview</h1>

      <div className="operator-rail-card operator-rail-state">
        <div className="operator-rail-state-row">
          <span className="operator-rail-state-ic" aria-hidden="true">
            {stateTone === "ready" ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
          </span>
          <div>
            <p className="operator-rail-eyebrow">Current state</p>
            <h2>{model.Headline}</h2>
          </div>
        </div>
        <p className="operator-rail-msg">{model.SupportingMessage}</p>
        <div className="operator-rail-meter">
          <div className="operator-rail-meter-label">
            <span>Readiness</span>
            <span className="operator-rail-mono">{ready} / {total} ready</span>
          </div>
          <div
            className="operator-rail-track"
            role="img"
            aria-label={`${ready} ready, ${blocked} blocked, ${unchecked} not checked`}
          >
            <i className="ready" style={{ width: pct(ready) }} />
            <i className="blocked" style={{ width: pct(blocked) }} />
            <i className="unchecked" style={{ width: pct(unchecked) }} />
          </div>
        </div>
      </div>

      <div className="operator-rail-card operator-rail-next">
        <p className="operator-rail-eyebrow">Next action</p>
        <button
          className="operator-rail-primary"
          data-testid="operator-home-primary-action"
          disabled={!model.NextAction.Enabled || primaryBusy}
          onClick={onPrimaryAction}
          type="button"
        >
          <Pencil size={16} />
          <span>{primaryBusy ? "Opening..." : model.NextAction.Label}</span>
        </button>
        <button
          className="operator-rail-ghost"
          data-testid="operator-home-view-details"
          onClick={onViewDetails}
          type="button"
        >
          <Eye size={15} />
          <span>{detailsOpen ? "Hide device details" : "View all device details"}</span>
          <ChevronRight size={15} />
        </button>
      </div>

      <div className="operator-rail-card operator-rail-blockers" aria-label="Needs your attention">
        <h3>Needs your attention</h3>
        {model.AttentionItems.length === 0 ? (
          <p className="operator-rail-clear">Nothing needs operator action right now.</p>
        ) : (
          <>
            {visibleAttentionItems.map((item) => {
              const explanation = uniqueOperatorAttentionText(item.Explanation, [item.Label]);
              const action = uniqueOperatorAttentionText(item.Action, [item.Label, item.Explanation]);
              return (
                <div className="operator-rail-blocker" key={item.Id}>
                  <span className={`operator-rail-bic ${item.Severity === "blocking" ? "blocked" : "unchecked"}`} />
                  <div>
                    <b>{item.Label}</b>
                    {explanation && <div className="operator-rail-why">{explanation}</div>}
                    {action && <div className="operator-rail-fix">{action}</div>}
                  </div>
                </div>
              );
            })}
            {hiddenAttentionCount > 0 && (
              <p className="operator-rail-more">
                {hiddenAttentionCount} more {hiddenAttentionCount === 1 ? "item is" : "items are"} in device details.
              </p>
            )}
          </>
        )}
      </div>

      {(loading || error) && (
        <p className={error ? "operator-rail-feedback error" : "operator-rail-feedback"}>
          {error || "Refreshing readiness..."}
        </p>
      )}
    </section>
  );
}

function uniqueOperatorAttentionText(value: string, previousValues: string[]): string {
  const text = value.trim();
  if (!text) return "";
  const normalized = normalizeAttentionText(text);
  return previousValues.some((previous) => normalizeAttentionText(previous) === normalized) ? "" : text;
}

function normalizeAttentionText(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").replace(/[.!?]+$/g, "").trim();
}
