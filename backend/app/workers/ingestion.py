import os
import re
import shutil
import uuid

from langchain_community.document_loaders import Docx2txtLoader, PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import PointStruct, SparseVector

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_upload import DocumentUpload
from app.models.document_version import DocumentVersion
from app.services.broadcast import broadcast_sync
from app.services.embedding import embed_texts
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.celery_app import celery_app

CHUNK_SIZE = 384  # en tokens BGE-M3 (conforme spec Phase 2)
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


def version_dir(doc_id: str, version: int) -> str:
    """Dossier d'archive d'une version : {storage}/{doc_id}/v{n}/."""
    return os.path.join(settings.documents_storage_path, doc_id, f"v{version}")


def chemin_du_fichier(doc_id: str, filename: str, stored_path: str | None) -> str | None:
    """Chemin sur disque du fichier courant d'un document, ou None s'il a disparu.

    Le repli couvre les documents backfillés, dont le fichier est resté à la racine
    du dossier ``{doc_id}`` au lieu d'un sous-dossier ``v{n}/``.

    Prend des chaînes plutôt qu'un ``Document`` : le job de mise à jour l'appelle
    après avoir fermé sa session, où l'instance est détachée. Et il vit ici plutôt
    que dans ``api/v1/documents.py``, qui importe déjà le job — l'inverse fermerait
    le cycle.
    """
    if stored_path and os.path.isfile(stored_path):
        return stored_path
    repli = os.path.join(settings.documents_storage_path, doc_id, filename)
    return repli if os.path.isfile(repli) else None


def store_file(tmp_path: str, doc_id: str, filename: str, version: int = 1) -> str:
    """Copie le fichier de /tmp vers le stockage permanent de la version.

    Copie et non déplacement : après un ``move`` réussi, un retry Celery échouerait
    sur ``extract_text`` (fichier disparu) et boucherait jusqu'à ``max_retries``.
    Le temporaire n'est supprimé qu'une fois le job abouti.
    """
    dest_dir = version_dir(doc_id, version)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    shutil.copy2(tmp_path, dest_path)
    return dest_path


def point_id(doc_id: str, version: int, index: int) -> str:
    """Id de point déterministe : un retry réécrit les mêmes points au lieu d'en créer."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{version}:{index}"))


@celery_app.task(
    name="ingestion_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion",
)
def ingestion_job(
    self,
    file_path: str,
    filename: str,
    domaine: str,
    description: str = "",
    content_hash: str = "",
    uploaded_by: str | None = None,
    doc_id: str | None = None,
):
    # doc_id vient de l'appelant : le régénérer ici ferait naître un document
    # différent à chaque retry, chacun laissant ses chunks derrière lui.
    doc_id = doc_id or str(uuid.uuid5(uuid.NAMESPACE_DNS, str(self.request.id)))
    version = 1

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

        # Étape 4 — Stockage permanent, avant l'indexation : le chemin fait partie du
        # payload, l'écrire après imposerait un set_payload correctif et laisserait une
        # fenêtre où les points portent stored_path: None.
        stored_path = store_file(file_path, doc_id, filename, version)
        print(f"[INGESTION] Fichier stocké : {stored_path}")

        # Étape 5 — Indexation Qdrant (batch unique)
        print("[INGESTION] Indexation dans Qdrant...")
        points = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False)):
            points.append(
                PointStruct(
                    id=point_id(doc_id, version, i),
                    vector={
                        "dense": emb["dense"],
                        "sparse": SparseVector(
                            indices=emb["sparse"]["indices"],
                            values=emb["sparse"]["values"],
                        ),
                    },
                    payload={
                        "doc_id": doc_id,
                        "version": version,
                        "chunk_index": i,
                        "source": filename,
                        "domaine": domaine,
                        "contenu": chunk,
                        "stored_path": stored_path,
                        "description": description,
                        "content_hash": content_hash,
                        "uploaded_by": uploaded_by,
                    },
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"[INGESTION] ✅ {len(points)} points indexés dans Qdrant")

        # Étape 6 — Enregistrement en base
        db = SessionLocal()
        try:
            user_uuid = uuid.UUID(uploaded_by) if uploaded_by else None
            _enregistrer_document(
                db,
                doc_id=doc_id,
                version=version,
                filename=filename,
                domaine=domaine,
                description=description,
                content_hash=content_hash,
                stored_path=stored_path,
                nb_chunks=len(chunks),
                uploaded_by=user_uuid,
            )
            db.add(DocumentUpload(
                doc_id=doc_id,
                user_id=user_uuid,
                domaine=domaine,
                filename=filename,
            ))
            db.commit()
        finally:
            db.close()

        # Étape 7 — Le temporaire n'a plus d'utilité : plus aucun retry ne suivra
        if os.path.exists(file_path):
            os.remove(file_path)

        result = {
            "statut": "OK",
            "filename": filename,
            "doc_id": doc_id,
            "stored_path": stored_path,
            "nb_chunks": len(chunks),
        }

        if uploaded_by:
            broadcast_sync(
                f"sse:user:{uploaded_by}",
                "job_completed",
                {"job_id": self.request.id, "status": "SUCCESS", "nb_chunks": len(chunks)},
            )

        return result

    except Exception as exc:
        print(f"[INGESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc


def _enregistrer_document(db, *, doc_id, version, filename, domaine, description,
                          content_hash, stored_path, nb_chunks, uploaded_by) -> None:
    """Crée (ou met à jour, si un retry est passé par là) les lignes documents/versions."""
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if doc is None:
        doc = Document(doc_id=doc_id)
        db.add(doc)
    doc.version = version
    doc.filename = filename
    doc.domaine = domaine
    doc.description = description
    doc.content_hash = content_hash or None
    doc.stored_path = stored_path
    doc.nb_chunks = nb_chunks
    doc.statut = "ACTIF"
    doc.uploaded_by = uploaded_by

    ligne = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.doc_id == doc_id, DocumentVersion.version == version)
        .first()
    )
    if ligne is None:
        ligne = DocumentVersion(doc_id=doc_id, version=version)
        db.add(ligne)
    ligne.filename = filename
    ligne.content_hash = content_hash or None
    ligne.stored_path = stored_path
    ligne.nb_chunks = nb_chunks
    ligne.taille_octets = os.path.getsize(stored_path) if os.path.isfile(stored_path) else None
    ligne.uploaded_by = uploaded_by
