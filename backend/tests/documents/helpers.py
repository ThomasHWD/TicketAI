"""Helpers et constantes partagés entre les fichiers de tests documents."""

import io
import os
import uuid
from unittest.mock import MagicMock

API = "/api/v1"

# Contenu minimal valide pour chaque format
_PDF_MAGIC = b"%PDF-1.4 fake content"
_DOCX_MAGIC = b"PK\x03\x04" + b"\x00" * 100  # archive ZIP minimale
_MD_CONTENT = b"# Titre\n\nContenu de test."

_TEXTE_V1 = (
    b"Le teletravail est limite a 2 jours par semaine, sur accord du manager.\n\n"
    b"La demande se fait via le portail RH, au moins 5 jours ouvres a l'avance."
)
_TEXTE_V2 = _TEXTE_V1.replace(b"2 jours", b"3 jours")

_ARTICLE_AJOUTE = b"Article 7 bis : le teletravail est suspendu pendant les periodes de forte activite."
_ARTICLE_ABROGE = b"Article 9 : une prime de 20 euros par mois compense les frais d'electricite du domicile."


def _upload(
    client,
    *,
    domaine="IT",
    filename="doc.md",
    content=_MD_CONTENT,
    content_type="text/plain",
    description="",
    force_nouveau=False,
):
    """Helper qui poste un fichier vers POST /documents."""
    params = f"domaine={domaine}"
    if description:
        params += f"&description={description}"
    if force_nouveau:
        params += "&force_nouveau=true"
    return client.post(
        f"{API}/documents?{params}",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def _job_kwargs(mock_job) -> dict:
    """Arguments du dernier apply_async — la tâche est appelée en tout-kwargs."""
    return mock_job.apply_async.call_args.kwargs["kwargs"]


def _make_point(doc_id, chunk_index=0):
    p = MagicMock()
    p.payload = {
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "contenu": f"Contenu chunk {chunk_index}",
    }
    p.id = str(uuid.uuid4())
    return p


def _doc_en_base(db, **overrides):
    """Insère une ligne `documents` prête à l'emploi."""
    from app.models.document import Document

    champs = {
        "doc_id": str(uuid.uuid4()),
        "filename": "charte.md",
        "domaine": "IT",
        "description": "",
        "nb_chunks": 3,
        "version": 1,
        "statut": "ACTIF",
    }
    champs.update(overrides)
    doc = Document(**champs)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _preview(client, doc_id, content=_TEXTE_V2, filename="charte.md"):
    return client.post(
        f"{API}/documents/{doc_id}/versions/preview",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def _doc_avec_fichier(db, tmp_path, contenu=_TEXTE_V1, **overrides):
    """Document dont le fichier de la version courante existe vraiment sur disque.

    C'est la condition de l'analyse des ajouts : sans ce fichier, il n'y a pas de
    texte de référence à comparer.
    """
    chemin = tmp_path / "courant.md"
    chemin.write_bytes(contenu)
    return _doc_en_base(db, domaine="RH", content_hash="hash-v1", stored_path=str(chemin), **overrides)


def _admin_id(db):
    from app.models.user import User

    return db.query(User).filter(User.role == "ADMIN").first().id


def _reponse_sur_chunk(db, doc_id, *, chunk_index, domaine="IT", nb_validations=3):
    """Réponse canonique validée s'appuyant sur un chunk précis du document."""
    from app.models.reponse import Reponse
    from app.models.reponse_chunk import ReponseChunk
    from app.models.ticket import Ticket

    ticket = Ticket(question="Combien de jours de télétravail ?", domaine=domaine, statut_job="TERMINÉ")
    db.add(ticket)
    db.flush()
    reponse = Reponse(
        ticket_id=ticket.id,
        contenu="Deux jours.",
        source="LLM",
        statut="VALIDÉE",
        canonique=True,
        nb_validations=nb_validations,
    )
    db.add(reponse)
    db.flush()
    db.add(ReponseChunk(reponse_id=reponse.id, doc_id=doc_id, chunk_index=chunk_index))
    db.commit()
    return reponse


def _version_en_base(db, doc, version, *, contenu=_TEXTE_V1, racine=None, **overrides):
    """Insère une ligne `document_versions`, avec son fichier archivé sur disque."""
    from app.models.document_version import DocumentVersion

    chemin = None
    if racine is not None:
        dossier = os.path.join(str(racine), doc.doc_id, f"v{version}")
        os.makedirs(dossier, exist_ok=True)
        chemin = os.path.join(dossier, doc.filename)
        with open(chemin, "wb") as f:
            f.write(contenu)

    champs = {
        "doc_id": doc.doc_id,
        "version": version,
        "filename": doc.filename,
        "stored_path": chemin,
        "nb_chunks": 2,
        "taille_octets": len(contenu),
    }
    champs.update(overrides)
    v = DocumentVersion(**champs)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v
