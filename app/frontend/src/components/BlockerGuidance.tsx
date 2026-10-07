import { Link } from "react-router-dom";
import type { BlockerAction, BlockerDetail } from "../api";

/*
 * Every blocker says what's wrong and how to get past it. The plain string is always shown;
 * the backend's guidance (services/blocker_guidance.py) adds "How to fix" and, where the app can
 * do the fix itself, one button. Guidance never approves anything or bypasses a blocker.
 */

export type GuidanceHandlers = Partial<Record<Exclude<BlockerAction, "none" | "open_connection" | "select_package">, () => void>>;

const buttonLabel: Record<string, string> = {
  read_again: "Read again",
  prepare_again: "Prepare again",
  narrow_scope_firmware: "Only update the iLO firmware",
  check_status: "Check status",
};
const kindLabel: Record<BlockerDetail["fix_kind"], string> = { app: "The app can fix this", physical: "Needs a hands-on fix", wait: "Wait for it", vendor: "Needs HPE's guidance" };

export function BlockerGuidance({ blockers, details, handlers = {}, deviceId, title = "Can't continue yet" }: {
  blockers: string[]; details?: BlockerDetail[]; handlers?: GuidanceHandlers; deviceId?: string; title?: string;
}) {
  if (!blockers.length) return null;
  const byText = new Map((details ?? []).map(item => [item.text, item]));
  // Several blockers can share one fix; show each distinct action button once, after the list.
  const shown = new Set<string>();
  return <div className="bg-box" role="note" aria-label={title}>
    <strong>{title}</strong>
    <ul>{blockers.map(text => {
      const detail = byText.get(text);
      const action = detail?.action && detail.action !== "none" ? detail.action : null;
      const first = action && !shown.has(action);
      if (action) shown.add(action);
      return <li key={text}>
        <span className="bg-text">{text}</span>
        {detail && <span className="bg-fix"><b>How to fix:</b> {detail.fix} <small className={`bg-kind bg-kind-${detail.fix_kind}`}>{kindLabel[detail.fix_kind]}</small></span>}
        {first && action === "open_connection" && <Link className="secondary-action bg-act" to={`/setup/connect${deviceId ? `?device=${encodeURIComponent(deviceId)}` : ""}`}>Open connection settings</Link>}
        {first && action === "select_package" && <Link className="secondary-action bg-act" to="/setup/check-firmware">Choose the SPP</Link>}
        {first && action && action in buttonLabel && handlers[action as keyof GuidanceHandlers] && <button type="button" className="secondary-action bg-act" onClick={handlers[action as keyof GuidanceHandlers]}>{buttonLabel[action]}</button>}
      </li>;
    })}</ul>
  </div>;
}
