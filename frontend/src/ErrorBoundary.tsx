import { Component, type ErrorInfo, type ReactNode } from 'react'

type ErrorBoundaryProps = {
  children: ReactNode
}

type ErrorBoundaryState = {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = {
    hasError: false,
    message: '',
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      message: error.message || 'The dashboard hit an unexpected rendering error.',
    }
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('GigOptimizer dashboard render error', error, info)
  }

  override render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <main className="shell loading">
        <section className="card" style={{ maxWidth: 760 }}>
          <p className="eyebrow">Recovery Mode</p>
          <h1>Dashboard rendering hit an unexpected issue.</h1>
          <p className="lede">{this.state.message}</p>
          <p className="inline-note">Refresh the page once. If it keeps happening, the backend is still reachable and your job history remains intact.</p>
        </section>
      </main>
    )
  }
}
