"""Extraction, nettoyage et découpage de texte pour l'ingestion et les diff."""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 384
CHUNK_OVERLAP = 128

_splitter = None


def get_splitter() -> RecursiveCharacterTextSplitter:
    """Splitter basé sur le tokenizer BGE-M3 : chunk_size/overlap comptés en tokens."""
    global _splitter
    if _splitter is None:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
        _splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", " ", ""],
        )
    return _splitter


def clean_text(text: str) -> str:
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(file_path) -> list[str]:
    """Extrait le texte d'un fichier PDF, DOCX, TXT, MD."""
    import os

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Fichier non trouvé : {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        from langchain_community.document_loaders import PyMuPDFLoader
        loader = PyMuPDFLoader(file_path)
        docs = loader.load()
        return [clean_text(doc.page_content) for doc in docs]

    if ext == ".docx":
        from langchain_community.document_loaders import Docx2txtLoader
        loader = Docx2txtLoader(file_path)
        docs = loader.load()
        return [clean_text(doc.page_content) for doc in docs]

    if ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8") as f:
            return [clean_text(f.read())]

    raise ValueError(f"Type de fichier non supporté : {ext}")


def chunk_text(pages: list[str]) -> list[str]:
    """Découpe le texte en chunks de CHUNK_SIZE tokens BGE-M3."""
    return get_splitter().split_text("\n\n".join(pages))


def texte_complet(pages: list[str]) -> str:
    """Le texte tel que ``chunk_text`` le verra — la forme canonique pour les diff."""
    return "\n\n".join(pages)
