import hashlib
import random

import numpy as np


def embed_texts_mock(texts: list[str]) -> list[dict]:
    results = []
    for text in texts:
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)

        dense = np.array([rng.uniform(-1, 1) for _ in range(1024)], dtype=np.float32)

        nb_tokens = min(len(text.split()), 20)
        indices = rng.sample(range(30000), nb_tokens)
        values = np.array(
            [rng.uniform(0, 1) for _ in range(nb_tokens)], dtype=np.float32
        )

        results.append(
            {"dense": dense, "sparse": {"indices": indices, "values": values}}
        )
    return results
