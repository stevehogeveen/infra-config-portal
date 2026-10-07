import { Component, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

/*
 * One page failing to render must not blank the whole app: the header, kit menu and navigation
 * stay usable, and the page says plainly that it hit a problem. Moving to another page resets it.
 */
class Boundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (!this.state.error) return this.props.children;
    return <section className="page-error" role="alert" aria-label="Page problem">
      <h1>This page hit a problem</h1>
      <p>Nothing was sent to any equipment. Other pages still work; use the navigation above, or reload this page.</p>
      <details><summary>Technical detail</summary><code>{this.state.error.message}</code></details>
      <button type="button" className="primary-action" onClick={() => window.location.reload()}>Reload page</button>
    </section>;
  }
}

export function PageErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <Boundary key={location.pathname}>{children}</Boundary>;
}
