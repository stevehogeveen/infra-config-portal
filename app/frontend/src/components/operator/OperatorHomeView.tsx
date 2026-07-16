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
  const attentionDevices = model.DeviceSummary.filter((item) => item.NeedsAttention);
  const total = Math.max(0, model.Progress.Total);
  const ready = Math.max(0, Math.min(model.Progress.Ready, total));
  const blocked = Math.max(0, Math.min(attentionDevices.length, total - ready));
  const unchecked = Math.max(0, total - ready - blocked);
  const pct = (n: number) => (total > 0 ? `${(n / total) * 100}%` : "0%");
  const stateTone = model.DisplayState === "ready" ? "ready" : blocked > 0 ? "blocked" : "attention";

  return (
    <section
      className={`operator-rail operator-rail-${stateTone}`}
      aria-label="Operator Home status and next action"
      data-testid="operator-home"
    >
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
          disabled={!model.NextAction.Enabled || loading}
          onClick={onPrimaryAction}
          type="button"
        >
          <Pencil size={16} />
          <span>{loading ? "Opening..." : model.NextAction.Label}</span>
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
          model.AttentionItems.map((item) => (
            <div className="operator-rail-blocker" key={item.Id}>
              <span className={`operator-rail-bic ${item.Severity === "blocking" ? "blocked" : "unchecked"}`} />
              <div>
                <b>{item.Label}</b>
                <div className="operator-rail-why">{item.Explanation}</div>
                <div className="operator-rail-fix">{item.Action}</div>
              </div>
            </div>
          ))
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
