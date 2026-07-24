import { useNavigate } from "react-router-dom";

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center h-screen">
      <h1 className="text-6xl font-bold text-gray-800 dark:text-gray-100">
        404
      </h1>
      <p className="text-xl text-gray-600 dark:text-gray-400 mt-4">
        Oups ! La page que vous recherchez n'existe pas.
      </p>
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mt-6 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition"
      >
        Retour à l'accueil
      </button>
    </div>
  );
}
