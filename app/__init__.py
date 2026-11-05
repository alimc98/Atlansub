"""Atlansub package."""
from __future__ import annotations

import os

# OpenBLAS (used by numpy) reserves a buffer for every CPU thread it thinks it
# can use. On a machine with a busy commit limit that reservation can be large
# enough to stop the speech model from loading. ctranslate2 does the heavy work
# with its own thread pool, so a single BLAS thread costs nothing and saves
# hundreds of megabytes.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
