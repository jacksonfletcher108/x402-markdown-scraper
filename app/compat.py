"""Stubs for native extras that do not yet ship wheels on Python 3.15."""

from __future__ import annotations

import sys
import types


def _unsupported(*_args, **_kwargs):
    raise RuntimeError(
        "This operation needs the native ckzg module, which is not available "
        "on this Python build. Use Python 3.12 or 3.13 for full EVM signing."
    )


def install_optional_stubs() -> None:
    if "ckzg" in sys.modules:
        return
    stub = types.ModuleType("ckzg")
    stub.blob_to_kzg_commitment = _unsupported
    stub.compute_blob_kzg_proof = _unsupported
    stub.compute_cells_and_kzg_proofs = _unsupported
    stub.load_trusted_setup = _unsupported
    sys.modules["ckzg"] = stub
