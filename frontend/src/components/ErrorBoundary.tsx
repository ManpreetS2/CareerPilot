import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

type Props = {
  children: ReactNode;
  /** Shown above the reset button. Keep this specific to where the boundary sits
   * (e.g. "This page" vs "CareerPilot") so the user knows how much just broke. */
  scope: string;
};

type State = {
  error: Error | null;
};

/** Class component is required here — React only supports catching render
 * errors via getDerivedStateFromError/componentDidCatch, no hook equivalent
 * exists. Catches errors in the render tree below it; does not catch errors
 * in event handlers, async code, or errors thrown outside React's render
 * (those are handled where they occur, e.g. ErrorBanner for fetch failures). */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Message and component stack only — never log props/state, which may
    // carry candidate or application data.
    console.error(`[ErrorBoundary:${this.props.scope}]`, error.message, info.componentStack);
  }

  private reset = () => {
    this.setState({ error: null });
  };

  render() {
    if (!this.state.error) {
      return this.props.children;
    }
    return (
      <div className="card mx-auto my-8 flex max-w-xl flex-col items-start gap-4 border-rose-300/70 bg-rose-50/80 p-8 text-center dark:border-rose-800 dark:bg-rose-950/30">
        <div className="flex w-full flex-col items-center gap-3 text-center">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-danger-600 dark:bg-rose-900/40 dark:text-rose-200">
            <AlertTriangle className="h-6 w-6" aria-hidden />
          </span>
          <h2 className="font-display text-xl font-semibold text-ink-950 dark:text-ink-50">
            {this.props.scope} hit an unexpected error
          </h2>
          <p className="max-w-md text-sm text-ink-600 dark:text-ink-300">
            Nothing was submitted or lost — your saved data is safe. Try again, and if it keeps
            happening, refresh the page.
          </p>
        </div>
        <button type="button" className="btn-primary mx-auto" onClick={this.reset}>
          Try again
        </button>
      </div>
    );
  }
}
