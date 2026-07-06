import os
import re
import shutil
import uuid

from langchain_community.document_loaders import Docx2txtLoader, PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import PointStruct, SparseVector

from app.config import settings
from app.services.embedding import embed_texts
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.celery_app import celery_app

CHUNK_SIZE = 384     # en tokens BGE-M3 (conforme spec Phase 2)
CHUNK_OVERLAP = 128  # en tokens BGE-M3

_splitter = None


def get_splitter() -> RecursiveCharacterTextSplitter:
    """Splitter basé sur le tokenizer BGE-M3 : chunk_size/overlap comptés en tokens,
    pas en caractères (le seuil cosinus est calibré sur des chunks de 384 tokens)."""
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
    # Supprime les numéros de page isolés
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    # Supprime les espaces multiples
    text = re.sub(r" +", " ", text)
    # Supprime les lignes vides multiples
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Supprime les headers/footers répétitifs (ligne < 5 mots répétée)
    text = text.strip()
    return text


def extract_text(file_path) -> list[str]:
    """Extrait le texte d'un fichier PDF, DOCX, TXT, MD"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Fichier non trouvé : {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        loader = PyMuPDFLoader(file_path)
        docs = loader.load()
        return [clean_text(doc.page_content) for doc in docs]

    elif ext == ".docx":
        loader = Docx2txtLoader(file_path)
        docs = loader.load()
        return [clean_text(doc.page_content) for doc in docs]

    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8") as f:
            return [clean_text(f.read())]
    else:
        raise ValueError(f"Type de fichier non supporté : {ext}")


def chunk_text(pages: list[str]) -> list[str]:
    """Découpe le texte en chunks de CHUNK_SIZE tokens BGE-M3"""
    return get_splitter().split_text("\n\n".join(pages))


def store_file(tmp_path: str, doc_id: str, filename: str) -> str:
    """Déplace le fichier de /tmp vers le stockage permanent."""
    dest_dir = os.path.join(settings.documents_storage_path, doc_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    shutil.move(tmp_path, dest_path)
    return dest_path


@celery_app.task(
    name="ingestion_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion",
)
def ingestion_job(self, file_path: str, filename: str, domaine: str):
    doc_id = str(uuid.uuid4())
    stored_path = None

    try:
        print(f"📄 --- DÉBUT DE L'INGESTION DU FICHIER '{filename}' ---")

        # Étape 1 — Extraction
        pages = extract_text(file_path)
        print(f"[INGESTION] {len(pages)} pages extraites")

        # Étape 2 — Chunking
        chunks = chunk_text(pages)
        print(f"[INGESTION] {len(chunks)} chunks générés")

        # Étape 3 — Embedding
        print(f"[INGESTION] Embedding de {len(chunks)} chunks...")
        embeddings = embed_texts(chunks, is_query=False)
        print("[INGESTION] Embeddings générés")

        # Étape 4 — Indexation Qdrant (batch unique)
        print("[INGESTION] Indexation dans Qdrant...")
        points = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": emb["dense"],
                        "sparse": SparseVector(
                            indices=emb["sparse"]["indices"],
                            values=emb["sparse"]["values"],
                        ),
                    },
                    payload={
                        "doc_id": doc_id,
                        "chunk_index": i,
                        "source": filename,
                        "domaine": domaine,
                        "contenu": chunk,
                        "stored_path": stored_path,
                    },
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"[INGESTION] ✅ {len(points)} points indexés dans Qdrant")

        # Étape 5 — Stockage permanent
        stored_path = store_file(file_path, doc_id, filename)
        print(f"[INGESTION] Fichier stocké : {stored_path}")

        return {
            "statut": "OK",
            "filename": filename,
            "doc_id": doc_id,
            "stored_path": stored_path,
            "nb_chunks": len(chunks),
        }

    except Exception as exc:
        print(f"[INGESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
