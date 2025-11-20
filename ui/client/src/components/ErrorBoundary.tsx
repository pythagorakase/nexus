/**
 * Error Boundary component for graceful error handling.
 *
 * Catches React component errors and displays a fallback UI with
 * error details and recovery options.
 */

import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReload = () => {
    window.location.reload();
  };

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
          <div className="max-w-2xl w-full space-y-6">
            <Alert variant="destructive">
              <AlertCircle className="h-5 w-5" />
              <AlertTitle className="text-lg font-semibold">Application Error</AlertTitle>
              <AlertDescription className="mt-2">
                <p className="mb-4">
                  The NEXUS interface encountered an unexpected error. This has been logged and can be
                  reported to the development team.
                </p>
                {this.state.error && (
                  <div className="mt-4 p-4 bg-background/50 rounded border border-destructive/20 font-mono text-xs overflow-auto max-h-48">
                    <div className="font-semibold mb-2 text-destructive">Error Details:</div>
                    <div className="text-muted-foreground">{this.state.error.toString()}</div>
                    {this.state.errorInfo && (
                      <details className="mt-2">
                        <summary className="cursor-pointer text-destructive hover:underline">
                          Component Stack
                        </summary>
                        <pre className="mt-2 text-muted-foreground whitespace-pre-wrap">
                          {this.state.errorInfo.componentStack}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
                <div className="mt-6 flex gap-3">
                  <Button onClick={this.handleReload} variant="default">
                    Reload Application
                  </Button>
                  <Button onClick={this.handleReset} variant="outline">
                    Try to Recover
                  </Button>
                </div>
              </AlertDescription>
            </Alert>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
