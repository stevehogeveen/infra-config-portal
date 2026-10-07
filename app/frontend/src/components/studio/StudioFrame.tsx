import type { ReactNode } from "react";
import { StudioRail } from "./StudioRail";
import { GuideFrameProvider, useGuideFrame } from "./Guide";

/** Build-steps rail, guide slot and screen. The right evidence drawer was removed at Steve's request (2026-09-29). */
export function StudioFrame({ viewing, defaultGuide, children, className = "" }: { viewing: number | null; defaultGuide?: ReactNode; children: ReactNode; className?: string }) {
  const frame = useGuideFrame();
  return <div className={`sd-frame ${className}`}>
    <StudioRail viewing={viewing} />
    <div className="sd-main">
      <div className="sd-guide-slot" ref={frame.ref} />
      {!frame.claimed && defaultGuide}
      <GuideFrameProvider value={frame.value}>{children}</GuideFrameProvider>
    </div>
  </div>;
}
