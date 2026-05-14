import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
  componentStack: string | null;
}

/**
 * ErrorBoundary global. Sem ele, qualquer runtime error num componente
 * desmonta a árvore inteira e a página fica preta. Aqui pega o erro,
 * exibe mensagem + stack e oferece "Recarregar".
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, componentStack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ componentStack: info.componentStack ?? null });
    console.error('[ErrorBoundary]', error, info);
  }

  reset = () => this.setState({ error: null, componentStack: null });

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="min-h-screen bg-background px-4 py-10">
        <div className="mx-auto max-w-2xl space-y-4">
          <h1 className="text-2xl font-semibold text-destructive">
            Algo deu errado
          </h1>
          <p className="text-sm text-muted-foreground">
            A página crashou em runtime. O erro abaixo ajuda a diagnosticar.
          </p>

          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4">
            <div className="font-mono text-sm font-medium">
              {this.state.error.name}: {this.state.error.message}
            </div>
            {this.state.error.stack && (
              <pre className="mt-2 max-h-64 overflow-auto text-xs text-muted-foreground">
                {this.state.error.stack}
              </pre>
            )}
          </div>

          {this.state.componentStack && (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">Component stack</summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded-md border p-2">
                {this.state.componentStack}
              </pre>
            </details>
          )}

          <div className="flex gap-2">
            <button
              onClick={this.reset}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm hover:bg-muted"
            >
              Tentar de novo
            </button>
            <button
              onClick={() => window.location.assign('/')}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm hover:bg-muted"
            >
              Voltar à home
            </button>
          </div>
        </div>
      </div>
    );
  }
}
