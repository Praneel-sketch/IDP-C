import numpy as np
import pytest

from citychange.landstate import (
    BUILT,
    CROPS,
    NODATA,
    SOURCE_TO_STATE,
    VEGETATION,
    WATER,
    remap_to_states,
)


def test_remap_known_codes():
    src = np.array([[1, 2, 4], [5, 7, 11], [0, 10, 8]], dtype=np.uint8)
    out = remap_to_states(src)
    assert out[0, 0] == WATER
    assert out[0, 1] == VEGETATION  # trees
    assert out[0, 2] == VEGETATION  # flooded vegetation
    assert out[1, 0] == CROPS
    assert out[1, 1] == BUILT
    assert out[1, 2] == VEGETATION  # rangeland
    assert out[2, 0] == NODATA  # nodata stays nodata
    assert out[2, 1] == NODATA  # clouds are unobservable, not a land state


def test_remap_unknown_code_becomes_nodata():
    src = np.array([[3, 6, 200]], dtype=np.uint8)  # codes absent from the product
    out = remap_to_states(src)
    assert (out == NODATA).all()


def test_remap_rejects_wrong_dtype():
    with pytest.raises(ValueError):
        remap_to_states(np.array([[1.0]]))


def test_mapping_covers_all_product_codes():
    assert set(SOURCE_TO_STATE) == {0, 1, 2, 4, 5, 7, 8, 9, 10, 11}
