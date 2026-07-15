import { AlertTriangle, CheckCircle2, ChevronRight, Eye, Play } from "lucide-react";

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
  const healthyCount = model.DeviceSummary.length - attentionDevices.length;

  return (
    <section className={`operator-home operator-home-${model.DisplayState}`} aria-label="Operator Home" data-testid="operator-home">
      <div className="operator-home-main">
        <div className="operator-home-copy">
          <p className="operator-kicker">Selected kit</p>
          <h1>Overview</h1>
          <strong>{model.KitName}</strong>
          <span>{model.CurrentPhase}</span>
        </div>
        <div className="operator-home-progress" aria-label="Canonical readiness result">
          <span>{model.Progress.Label}</span>
          <progress max={model.Progress.Total} value={model.Progress.Ready} aria-label="Readiness progress" />
        </div>
      </div>

      <div className="operator-home-state">
        <StateIcon state={model.DisplayState} />
        <div>
          <p className="operator-kicker">Current state</p>
          <h2>{model.Headline}</h2>
          <p>{model.SupportingMessage}</p>
        </div>
      </div>

      <div className="operator-home-device-summary" aria-label="Compact device summary">
        <div>
          <strong>{healthyCount}</strong>
          <span>{healthyCount === 1 ? "device ready" : "devices ready"}</span>
        </div>
        {attentionDevices.length === 0 ? (
          <p>No device-specific exceptions are open.</p>
        ) : (
          <ul>
            {attentionDevices.map((item) => (
              <li key={`${item.Name}-${item.Role}`}>
                <strong>{item.Name}</strong>
                <span>{item.State}</span>
                <small>{item.Detail}</small>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="operator-home-attention" aria-label="Actionable blockers">
        {model.AttentionItems.length === 0 ? (
          <p>Nothing needs operator action right now.</p>
        ) : (
          model.AttentionItems.map((item) => (
            <article className={`operator-home-attention-item ${item.Severity}`} key={item.Id}>
              <span>{item.Severity === "blocking" ? "Action required" : "Review"}</span>
              <h3>{item.Label}</h3>
              <p>{item.Explanation}</p>
              <small>{item.Action}</small>
            </article>
          ))
        )}
      </div>

      {(loading || error) && (
        <p className={error ? "operator-home-feedback error" : "operator-home-feedback"}>
          {error || "Refreshing readiness..."}
        </p>
      )}

      <div className="operator-home-actions">
        <button
          className="operator-home-primary"
          data-testid="operator-home-primary-action"
          disabled={!model.NextAction.Enabled || loading}
          onClick={onPrimaryAction}
          type="button"
        >
          <Play size={16} />
          <span>{loading ? "Opening..." : model.NextAction.Label}</span>
        </button>
        <button
          className="operator-home-secondary"
          data-testid="operator-home-view-details"
          onClick={onViewDetails}
          type="button"
        >
          <Eye size={16} />
          <span>{detailsOpen ? "Hide Details" : "View Details"}</span>
          <ChevronRight size={15} />
        </button>
      </div>
    </section>
  );
}

function StateIcon({ state }: { state: OperatorHomeModel["DisplayState"] }) {
  if (state === "ready") return <CheckCircle2 aria-hidden="true" size={30} />;
  return <AlertTriangle aria-hidden="true" size={30} />;
}
