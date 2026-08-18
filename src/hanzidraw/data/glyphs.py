"""Reading stored geometry back out as drawable glyphs.

The bridge between the store's em-unit medians and ``render.glyph``. It lives
here rather than in ``output.base`` because it is a *store reader*: the output
protocol should not have to know that a database exists.
"""

from __future__ import annotations

from ..render.glyph import Glyph, glyph_from_em
from .store import Store


def load_glyph(store: Store, codepoint: int) -> Glyph:
    """The stored medians for one character, as unit-box geometry."""
    return glyph_from_em(store.medians(codepoint))
