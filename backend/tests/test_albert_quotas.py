"""GET /admin/albert-quotas against Albert's current /me/usage contract (measured 29/09/2026).

end_time is required, buckets carry no model, and the `models` filter only knows canonical ids — an alias from our
config comes back empty. The previous code read per-event `model`/`created` fields and showed an empty panel.
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration

API = "/api/v1"

CATALOGUE = [
    {"id": "gpt-oss-120b", "aliases": ["openai/gpt-oss-120b"]},
    {"id": "gemma-4-31b-it", "aliases": ["google/gemma-4-31B-it"]},
]
USAGE = {
    "gpt-oss-120b": [{"requests": 79, "prompt_tokens": 94366}],
    "gemma-4-31b-it": [{"requests": 107, "prompt_tokens": 33805}],
}


def _albert(url, params=None, **_):
    if url.endswith("/models"):
        return SimpleNamespace(json=lambda: {"data": CATALOGUE})
    if url.endswith("/me/info"):
        return SimpleNamespace(is_success=True, json=lambda: {"limits": [{"type": "rpd", "value": 1000}]})
    if url.endswith("/me/usage"):
        if "end_time" not in (params or {}):
            return SimpleNamespace(
                raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("422")), is_success=False
            )
        seaux = [s for m in params.get("models") or [] for s in USAGE.get(m, [])]
        return SimpleNamespace(raise_for_status=lambda: None, is_success=True, json=lambda: {"data": seaux})
    raise AssertionError(url)


def test_consommation_du_jour_ventilee_par_modele(client, user_factory, auth_header, monkeypatch):
    import app.api.v1.admin.health as health

    monkeypatch.setattr(health.httpx, "get", _albert)
    monkeypatch.setattr(health.settings, "albert_llm_model_name", "openai/gpt-oss-120b")
    monkeypatch.setattr(health.settings, "albert_garde_model_name", "gemma-4-31b-it")
    for champ in (
        "albert_reverif_model_name",
        "albert_tag_model_name",
        "albert_contexte_model_name",
        "albert_embeddings_model_name",
        "albert_reranker_model_name",
    ):
        monkeypatch.setattr(health.settings, champ, "")

    resp = client.get(f"{API}/admin/albert-quotas", headers=auth_header(user_factory("ADMIN")))

    assert resp.status_code == 200
    par_modele = {m["nom"]: (m["requetes_aujourd_hui"], m["tokens_aujourd_hui"]) for m in resp.json()["modeles"]}
    assert par_modele == {"gpt-oss-120b": (79, 94366), "gemma-4-31b-it": (107, 33805)}
