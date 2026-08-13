import { describe, expect, it } from "vitest";

import { MAX_SIZE_MB, formatSize, validateFile } from "./documentUpload";

/** Fabrique un `File` d'une taille donnée sans allouer les octets pour de vrai. */
function fichier(nom: string, octets = 1024): File {
  const f = new File(["x"], nom);
  Object.defineProperty(f, "size", { value: octets });
  return f;
}

describe("formatSize", () => {
  it("bascule des Ko aux Mo au seuil du mégaoctet", () => {
    expect(formatSize(1023)).toBe("1 Ko");
    expect(formatSize(1024 * 1024 - 1)).toBe("1024 Ko");
    expect(formatSize(1024 * 1024)).toBe("1.0 Mo");
    expect(formatSize(2.5 * 1024 * 1024)).toBe("2.5 Mo");
  });
});

describe("validateFile", () => {
  it("accepte les quatre extensions supportées", () => {
    for (const nom of ["charte.pdf", "note.docx", "notes.txt", "guide.md"]) {
      expect(validateFile(fichier(nom))).toBeNull();
    }
  });

  it("ignore la casse de l'extension", () => {
    expect(validateFile(fichier("CHARTE.PDF"))).toBeNull();
  });

  it("refuse une extension non supportée", () => {
    expect(validateFile(fichier("archive.zip"))).toMatch(/Extension non supportée/);
  });

  it("refuse un fichier au-delà de la limite, et accepte pile à la limite", () => {
    const limite = MAX_SIZE_MB * 1024 * 1024;
    expect(validateFile(fichier("gros.pdf", limite))).toBeNull();
    expect(validateFile(fichier("gros.pdf", limite + 1))).toMatch(/trop volumineux/);
  });

  it("signale d'abord l'extension, même si le fichier est aussi trop gros", () => {
    expect(validateFile(fichier("gros.zip", 999 * 1024 * 1024))).toMatch(/Extension non supportée/);
  });
});
