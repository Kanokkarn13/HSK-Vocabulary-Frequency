import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangleIcon, RefreshIcon } from "./icons";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-[#faf8f6] px-4 dark:bg-ink-950">
        <div className="w-full max-w-sm rounded-2xl border border-ink-200 bg-white p-8 text-center shadow-sm dark:border-ink-800 dark:bg-ink-900">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-amber-600 dark:bg-amber-500/15 dark:text-amber-400">
            <AlertTriangleIcon className="h-6 w-6" />
          </div>
          <h1 className="font-display mt-4 text-lg font-semibold text-ink-900 dark:text-ink-50">
            เกิดข้อผิดพลาดบางอย่าง
          </h1>
          <p className="mt-1.5 text-sm text-ink-500 dark:text-ink-400">
            หน้านี้ไม่สามารถแสดงผลได้ กรุณาลองโหลดหน้าใหม่อีกครั้ง
          </p>
          <button
            onClick={this.handleReload}
            className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"
          >
            <RefreshIcon className="h-4 w-4" />
            โหลดหน้าใหม่
          </button>
        </div>
      </div>
    );
  }
}
