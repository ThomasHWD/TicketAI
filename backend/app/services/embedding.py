import os

from FlagEmbedding import BGEM3FlagModel

os.environ["TOKENIZERS_PARALLELISM"] = "false"

_model = None

def get_model() -> BGEM3FlagModel:
    global _model
    if _model is None:
        print("[EMBEDDING] Chargement BGE-M3 via FlagEmbedding...")
        _model = BGEM3FlagModel(
            'BAAI/BGE-M3',
            use_fp16=False,  # CPU — pas de fp16
        )
        print("[EMBEDDING] BGE-M3 prêt")
    return _model


def embed_texts(texts: list[str], is_query: bool = False) -> list[dict]:
    model = get_model()

    output = model.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    results = []
    for i in range(len(texts)):
        dense = output["dense_vecs"][i].tolist()

        sparse_weights = output["lexical_weights"][i]
        indices = [int(k) for k in sparse_weights.keys()]
        values = [float(v) for v in sparse_weights.values()]

        results.append({
            "dense": dense,
            "sparse": {"indices": indices, "values": values}
        })

    return results
