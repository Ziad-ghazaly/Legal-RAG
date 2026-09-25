# Rule 1 — Same embedding model everywhere

Fails if `system_meta` disagrees with config on `embedding_model`,
`embedding_dim`, or `normalizer_version`, or if any `chunks.embedding_model`
differs from the current one.

Script `check_embedding_consistency.py` supplied by brief author.
