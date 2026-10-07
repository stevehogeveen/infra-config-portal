// Small window events so the top bar and command palette can open existing dialogs
// (kit rename / save as / build reports, report an issue) without moving their state.
export type KitDialogMode = "rename" | "copy" | "reports";
export const KIT_DIALOG_EVENT = "studio:kit-dialog";
export const REPORT_ISSUE_EVENT = "studio:report-issue";

export function openKitDialog(mode: KitDialogMode) {
  window.dispatchEvent(new CustomEvent<KitDialogMode>(KIT_DIALOG_EVENT, { detail: mode }));
}

export function openIssueReporter() {
  window.dispatchEvent(new Event(REPORT_ISSUE_EVENT));
}
