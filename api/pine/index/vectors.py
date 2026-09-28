"""float32 little-endian vector storage helpers (ARCHITECTURE §4)."""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt


def pack_vec(vec: Sequence[float] | npt.NDArray[np.floating]) -> bytes:
    """Serialise a vector as float32 little-endian bytes."""
    return np.asarray(vec, dtype=np.float32).astype("<f4").tobytes()


def unpack_vec(data: bytes) -> npt.NDArray[np.float32]:
    """Read a packed float32 little-endian vector."""
    return np.frombuffer(data, dtype="<f4")
