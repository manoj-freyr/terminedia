import terminedia as TM
from terminedia.text.style import StyledSequence

import pytest

from conftest import rendering_test, fast_and_slow_render_mark

@pytest.mark.fixture
def styled_text():
    sc = TM.Screen((20, 10))
    sh = TM.shape((20, 10))
    sp1 = sc.data.sprites.add(sh)
    text_plane = sh.text[1]
    return sc, sh, text_plane


@pytest.mark.parametrize(*fast_and_slow_render_mark)
@rendering_test
def test_styled_sequence_is_rendered():
    sc, sh, text_plane = styled_text()
    msg = "Hello World!"
    aa = StyledSequence(msg, {}, text_plane)
    aa.render()
    sc.update()
    yield None
    for i, char in enumerate(msg):
        assert sc.data[i, 0].value == char
