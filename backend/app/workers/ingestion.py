import os

from celery import Task
from langchain_community.document_loaders import Docx2txtLoader, PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.workers.celery_app import celery_app

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


def extract_text(file_path) -> str:
    """Extrait le texte d'un fichier PDF, DOCX, TXT, MD"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Fichier non trouvé : {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        loader = PyMuPDFLoader(file_path)
        docs = loader.load()
        return [doc.page_content for doc in docs]

    elif ext == ".docx":
        loader = Docx2txtLoader(file_path)
        docs = loader.load()
        return [doc.page_content for doc in docs]

    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8") as f:
            return [f.read()]
    else:
        raise ValueError(f"Type de fichier non supporté : {ext}")


def chunk_text(pages: list[str]) -> list[str]:
    """Découpe le texte en chunks"""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    ).split_text("\n".join(pages))


@celery_app.task(
    name="ingestion_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion",
)
def ingestion_job(self: Task, file_path: str, filename: str, domaine: str):
    try:
        print(f"📄 --- DÉBUT DE L'INGESTION DU FICHIER '{filename}' ---")

        # 1. Extraction du texte
        pages = extract_text(file_path)
        print(f"[INGESTION] {len(pages)} pages extraites")

        # 2. Chunking du texte
        chunks = chunk_text(pages)
        print(f"[INGESTION] {len(chunks)} chunks générés")

        # TODO 3 + 4. Embedding et ingestion dans Qdrant
        return {"statut": "OK", "filename": filename, "nb_chunks": len(chunks)}

    except Exception as e:
        print(f"[INGESTION] ERREUR : {str(e)}")
        raise self.retry(exc=e) from e
