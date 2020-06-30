import inspect
from inspect import signature

import pytest

from terminedia.utils import combine_signatures, TaggedDict, HookList

def test_combine_signatures_works():
    context = {}
    def add_color(func):
        @combine_signatures(func)
        def wrapper(*args, color=None, **kwargs):
            nonlocal context
            context["color"] = color
            return func(*args, **kwargs)
        return wrapper
    @add_color
    def line(p1, p2):
        assert p1 == (0, 0)
        assert p2 == (10,10)

    sig = signature(line)

    assert 'p1' in  sig.parameters
    assert 'p2' in sig.parameters
    assert 'color' in sig.parameters
    assert sig.parameters['color'].kind == inspect._ParameterKind.KEYWORD_ONLY

    line((0,0), p2=(10,10), color="red")
    assert context["color"] == "red"


def test_tagged_dictionary_is_created():
    x = TaggedDict()
    assert not x


def test_tagged_dictionary_can_contain_simple_items():
    x = TaggedDict()
    x["simple"] = "simple"

    assert x["simple"] == ["simple"]

def test_tagged_dictionary_can_delete_simple_items():
    x = TaggedDict()
    x["simple"] = "simple"
    del x["simple"]

    with pytest.raises(KeyError):
        x["simple"]


def test_tagged_dictionary_can_contain_items_with_2_tags():
    x = TaggedDict()
    x["first", "second"] = "element"

    assert x["first"] == ["element"]
    assert x["second"] == ["element"]


def test_tagged_dictionary_can_delete_itens_by_any_tag():
    x = TaggedDict()
    x["first", "second"] = "element"
    del x["first"]
    assert not x

    x["first", "second"] = "element"
    del x["second"]
    assert not x

    x["first", "second"] = "element"
    del x["second", "first"]
    assert not x

    x["first", "second"] = "element"
    with pytest.raises(KeyError):
        x["simple", "second", "third"]

    assert x


def test_tagged_dictionary_views_work():
    x = TaggedDict()
    y = x.view("animals")
    z = y.view("insects")

    z["0"] = "butterfly"
    z["1"] = "bee"
    assert len(z) == 2

    z1 = y.view("mammals")
    z1["0"] = "dog"

    w = x.view("things")
    w["0"] = "chair"

    assert len(z) == 2
    assert len(z1) == 1
    assert len(y) == 3

    assert len(w) == 1

    assert len(x) == 4

    assert set(x.values()) == {"chair", "dog", "bee", "butterfly"}
    assert set(x[()]) == {"chair", "dog", "bee", "butterfly"}


def test_tagged_dictionary_views_added_tag_reflects_on_other_tags():
    x = TaggedDict()
    y = x.view("animals")
    z = y.view("insects")
    z1 = y.view("mammals")

    assert not y

    z["mammals"] = "spyderman"

    assert y
    assert len(y) == 1
    assert len(z) == 1

    assert x["insects", "mammals"] == ["spyderman"]

def test_tagged_dictionary_views_add_method():
    x = TaggedDict()
    y = x.view("animals")

    h = y.add("dog")

    assert h
    assert y[()] == ["dog"]
    assert x[()] == ["dog"]

    assert h in x
    del x[h]
    assert not x

def test_tagged_dictionary_views_add_method_unique_handles():
    x = TaggedDict()
    y = x.view("animals")

    h1 = y.add("dog")
    h2 = y.add("cat")

    assert h1 != h2


def test_tagged_dictionary_views_can_remove_by_value():
    x = TaggedDict()
    y = x.view("animals")

    h1 = y.add("dog")

    y.remove("dog")
    assert not y

    with pytest.raises(ValueError):
        y.remove("dog")

def test_hook_list_compares_eq_ok():
    from copy import copy
    a = HookList([1,2,3])
    b = HookList([1,2,3])

    assert a == b
    b.append(4)
    assert a != b
    b.pop()
    b[0] = 0
    assert a != b


def test_hook_list_shallow_copy_yields_a_copy():
    from copy import copy
    a = HookList([1,2,3])
    b = copy(a)
    c = a.copy()

    assert a == b
    assert a == c

    a.append(4)
    assert a != b
    assert a != c

def test_hook_list_shallow_copy_dont_trigger_side_effects():

    class DoubleList(HookList):
        def insert_hook(self, item):
            return 2 * item

    a = DoubleList([1,2,3])
    c = a.copy()

    assert a == c
