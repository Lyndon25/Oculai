import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";

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

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary] Uncaught render error:", error.message);
    console.error("[ErrorBoundary] Component stack:", info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex h-full items-center justify-center bg-canvas p-8">
          <div className="max-w-md text-center">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-red-200 bg-red-50">
              <AlertTriangle className="h-8 w-8 text-red-500" aria-hidden="true" />
            </div>
            <h1 className="font-display text-xl font-bold text-ink">
              界面发生错误
            </h1>
            <p className="mt-2 text-sm leading-6 text-ink-secondary">
              渲染组件时遇到了意外错误。您的数据和运行状态仍然安全。
            </p>
            {this.state.error && (
              <p className="mt-3 rounded-lg border border-red-100 bg-red-50/60 p-3 font-mono text-xs text-red-700 break-words">
                {this.state.error.message || "Unknown error"}
              </p>
            )}
            <div className="mt-6 flex items-center justify-center gap-3">
              <button
                type="button"
                className="btn-secondary"
                onClick={this.handleReset}
              >
                <RefreshCcw className="h-4 w-4" aria-hidden="true" />
                尝试恢复
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={this.handleReload}
              >
                重新加载
              </button>
            </div>
            <p className="mt-4 text-xs text-ink-muted">
              如果问题持续，请检查 Console 日志或重启应用。
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
