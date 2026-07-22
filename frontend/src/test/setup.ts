// Setup global des tests frontend (chargé via vite.config.ts → test.setupFiles).
// Ajoute les matchers jest-dom (`toBeInTheDocument`, etc.) et nettoie le DOM
// entre chaque test.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
