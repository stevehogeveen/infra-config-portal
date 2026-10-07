import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/*
 * The guide banner: one sentence, one primary action, one line saying what will not change.
 *
 * The frame (SetupJourney / My Rack) owns a slot at the top of the screen. A screen that knows
 * its own next step renders <Guide> and it is portalled into that slot; otherwise the frame
 * shows its default guide. Outside a frame (component harnesses) <Guide> renders in place.
 *
 * A component deeper in the screen can hoist its own existing primary action into the guide with
 * <GuidePrimary>, so the screen keeps exactly one primary instead of duplicating it.
 */

type FrameSlot = { element: HTMLElement | null; claim: () => () => void };
const FrameSlotContext = createContext<FrameSlot | null>(null);

type ActionSlot = { element: HTMLElement | null; claim: () => () => void };
const ActionSlotContext = createContext<ActionSlot | null>(null);

function useClaims() {
  const [claims, setClaims] = useState(0);
  const claim = useCallback(() => { setClaims(value => value + 1); return () => setClaims(value => value - 1); }, []);
  return [claims, claim] as const;
}

/** Used by the frame. Returns the slot ref, whether a screen has claimed it, and the context value. */
export function useGuideFrame() {
  const [element, setElement] = useState<HTMLElement | null>(null);
  const [claims, claim] = useClaims();
  const value = useMemo(() => ({ element, claim }), [element, claim]);
  return { ref: setElement, claimed: claims > 0, value };
}
export const GuideFrameProvider = FrameSlotContext.Provider;

/** Used by a screen that renders a guide: children below can hoist a primary into it. */
export function useGuideActions() {
  const [element, setElement] = useState<HTMLElement | null>(null);
  const [claims, claim] = useClaims();
  const value = useMemo(() => ({ element, claim }), [element, claim]);
  return { ref: setElement, hoisted: claims > 0, value };
}
export const GuideActionProvider = ActionSlotContext.Provider;

export type GuideProps = {
  eyebrow: ReactNode;
  say: ReactNode;
  reassure?: ReactNode;
  primary?: ReactNode;
  aside?: ReactNode;
  trail?: ReactNode[];
  label?: ReactNode;
  actionRef?: (element: HTMLElement | null) => void;
};

export function GuideBanner({ eyebrow, say, reassure, primary, aside, trail, label, actionRef }: GuideProps) {
  return <section className="sd-guide" aria-label="Your guide">
    <span className="sd-orb" aria-hidden="true" />
    <div className="sd-guide-text">
      <p className="sd-g-eyebrow">{eyebrow}</p>
      <p className="sd-say">{say}</p>
      {reassure && <p className="sd-reassure"><svg className="sd-ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.8l5 2v3.8c0 3.2-2.2 5.5-5 6.6-2.8-1.1-5-3.4-5-6.6V3.8z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /><path d="M5.8 8l1.6 1.6 2.9-3" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg><span>{reassure}</span></p>}
    </div>
    <div className="sd-g-act">
      <div className="sd-g-slot" ref={actionRef} />
      {primary}
      {aside && <span className="sd-g-aside">{aside}</span>}
    </div>
    {(trail?.length || label) ? <div className="sd-g-more">
      {!!trail?.length && <details className="sd-trail"><summary>How we got here · {trail.length} note{trail.length === 1 ? "" : "s"}</summary><ol>{trail.map((item, index) => <li key={index} className={index === trail.length - 1 ? "last" : undefined}>{item}</li>)}</ol></details>}
      {label && <p className="sd-newlabel">{label}</p>}
    </div> : null}
  </section>;
}

/** A screen's guide. Portalled into the frame's slot when there is one. */
export function Guide(props: GuideProps) {
  const frame = useContext(FrameSlotContext);
  useLayoutEffect(() => frame?.claim(), [frame?.claim]);
  const banner = <GuideBanner {...props} />;
  if (frame?.element) return createPortal(banner, frame.element);
  if (frame) return null;
  return banner;
}

/** Hoists an existing primary action into the nearest guide; renders in place without one. */
export function GuidePrimary({ children }: { children: ReactNode }) {
  const slot = useContext(ActionSlotContext);
  useLayoutEffect(() => slot?.claim(), [slot?.claim]);
  if (slot?.element) return createPortal(children, slot.element);
  return <>{children}</>;
}
