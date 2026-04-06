import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="rounded border border-error/20 bg-error/5 p-6">
          <h2 className="mb-2 text-lg font-semibold text-error">Something went wrong</h2>
          <pre className="text-xs text-text-muted">{this.state.error?.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
