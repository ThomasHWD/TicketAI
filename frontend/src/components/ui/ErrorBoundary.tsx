import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  erreur: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { erreur: false };

  static getDerivedStateFromError(): State {
    return { erreur: true };
  }

  render() {
    if (this.state.erreur) {
      return (
        <div className="fixed inset-0 flex flex-col items-center justify-center gap-4 bg-gray-50 dark:bg-[#0d0d0d]">
          <p className="text-gray-700 dark:text-gray-300 text-sm">
            Une erreur inattendue s'est produite.
          </p>
          <button
            className="px-4 py-2 rounded-md bg-emerald-600 text-white text-sm hover:bg-emerald-700"
            onClick={() => window.location.reload()}
          >
            Recharger la page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
