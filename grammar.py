from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from textwrap import indent
from typing import List, Dict, Union


class _DiscardMarker:
    def __repr__(self):
        return '_discard_marker'

    __instance__ = None

    def __new__(cls, *args, **kwargs):
        if cls.__instance__ is None:
            cls.__instance__ = super(_DiscardMarker, cls).__new__(cls, *args, **kwargs)
        return cls.__instance__


_discard_marker = _DiscardMarker()


class _InlineMarker:
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return f'{type(self).__name__}({self.data!r})'


class Tree:
    def __init__(self, name: str, children: List):
        self.name = name
        self.children = children

    def __repr__(self):
        return f'{type(self).__name__}({self.name!r}, {self.children!r})'

    def __str__(self):
        inner = "\n".join(str(c) for c in self.children)
        return f'{self.name}:\n{indent(inner, "    ")}'


class BaseGrammarNode(ABC):
    name: str = None
    discard: bool = None
    inline: bool = None
    _prepared: bool = False

    def __set_name__(self, owner, name):
        self.name = name

    def __or__(self, other):
        if isinstance(other, str):
            other = Symbol(other)
        return Option([self, other])

    def __ror__(self, other):
        if isinstance(other, str):
            other = Symbol(other)
        return Option([other, self])

    def __add__(self, other):
        if isinstance(other, str):
            other = Symbol(other)
        return Sequence([self, other])

    def __radd__(self, other):
        if isinstance(other, str):
            other = Symbol(other)
        return Sequence([other, self])

    def __getitem__(self, item):
        if isinstance(item, tuple):
            mi, ma = item
        else:
            mi = ma = item
        if mi is None:
            mi = 0
        return Repetition(self, mi, ma)

    @abstractmethod
    def parse(self, text: str):
        raise NotImplementedError

    @abstractmethod
    def copy(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def prepare(self):
        if not self._prepared:
            if self.discard is None:
                self.discard = isinstance(self, Symbol)
            else:
                self.discard = self.discard
            if self.inline is None:
                self.inline = self.name is None
            else:
                self.inline = self.inline
            self._prepared = True
            return True
        else:
            return False

    def update(self, inline: bool = None, discard: bool = None):
        if inline is not None:
            self.inline = inline
        if discard is not None:
            self.discard = discard

    def _build(self, r):
        if self.discard:
            return _discard_marker
        name = self.name or '<unnamed node>'
        r = [e for t in r for e in (t.data if isinstance(t, _InlineMarker) else
                                    () if t is _discard_marker else
                                    (t,))]
        if self.inline:
            return _InlineMarker(r)
        else:
            return Tree(name, r)


class Symbol(BaseGrammarNode):
    def __init__(self, text: str):
        self.text = text

    def __repr__(self):
        return f's({self.text!r})'

    def parse(self, text: str):
        if text.startswith(self.text):
            yield self._build((self.text,)), text[len(self.text):]

    def copy(self, **kwargs):
        c = self.__class__(self.text)
        c.update(**kwargs)
        return c

    def prepare(self):
        super(Symbol, self).prepare()


class Regex(BaseGrammarNode):
    def __init__(self, text: str):
        self.text = text
        self._re = re.compile(text)

    def __repr__(self):
        return f'r({self.text!r})'

    def parse(self, text: str):
        if m := self._re.match(text):
            yield self._build((m.group(0),)), text[m.end(0):]

    def copy(self, **kwargs):
        c = self.__class__(self.text)
        c.update(**kwargs)
        return c

    def prepare(self):
        super(Regex, self).prepare()


class Option(BaseGrammarNode):
    def __init__(self, options: List[BaseGrammarNode] = None):
        self.options = options or []

    def parse(self, text: str):
        for o in self.options:
            yield from ((self._build((r,)), t) for r, t in o.parse(text))

    def copy(self, **kwargs):
        c = self.__class__(self.options.copy())
        c.update(**kwargs)
        return c

    def prepare(self):
        if super(Option, self).prepare():
            for o in self.options:
                o.prepare()


class Sequence(BaseGrammarNode):
    def __init__(self, sequence: List[BaseGrammarNode]):
        self.sequence = sequence

    def __add__(self, other):
        if isinstance(other, str):
            other = Symbol(other)
        elif isinstance(other, Sequence):
            return Sequence([*self.sequence, *other.sequence])
        return Sequence([*self.sequence, other])

    def __radd__(self, other):
        if isinstance(other, str):
            other = Symbol(other)
        elif isinstance(other, Sequence):
            return Sequence([*other.sequence, *self.sequence])
        return Sequence([other, *self.sequence])

    def parse(self, text: str):
        stack = [((), self.sequence[0].parse(text))]
        while stack:
            try:
                r, t = next(stack[-1][1])
            except StopIteration:
                stack.pop()
            else:
                if len(stack) == len(self.sequence):
                    yield self._build((*stack[-1][0], r)), t
                else:
                    stack.append(((*stack[-1][0], r), self.sequence[len(stack)].parse(t)))

    def copy(self, **kwargs):
        c = self.__class__(self.sequence.copy())
        c.update(**kwargs)
        return c

    def prepare(self):
        if super(Sequence, self).prepare():
            for o in self.sequence:
                o.prepare()


class Repetition(BaseGrammarNode):
    def __init__(self, base: BaseGrammarNode, mi: int, ma: Union[int, None]):
        self.base = base
        self.mi = mi
        self.ma = ma

    def parse(self, text: str):
        if self.mi == 0:
            yield self._build(()), text
        stack = [((), self.base.parse(text))]
        while stack:
            try:
                r, t = next(stack[-1][1])
            except StopIteration:
                stack.pop()
            else:
                if len(stack) >= self.mi:
                    yield self._build((*stack[-1][0], r)), t
                    if self.ma is None or len(stack) < self.ma:
                        stack.append(((*stack[-1][0], r), self.base.parse(t)))
                else:
                    stack.append(((*stack[-1][0], r), self.base.parse(t)))

    def copy(self, **kwargs):
        c = self.__class__(self.base, self.mi, self.ma)
        c.update(**kwargs)
        return c

    def prepare(self):
        if super(Repetition, self).prepare():
            self.base.prepare()


SPECIAL_NAMES = {
    'r': Regex,
    's': Symbol,
    'i': lambda n: n.copy(inline=True),
    'd': lambda n: n.copy(discard=True),
}


class GrammarDict:
    def __init__(self, productions: Dict[str, Option] = None):
        self.productions = defaultdict(Option, productions)
        self.special = {}

    def __getitem__(self, item):
        if not isinstance(item, str):
            raise TypeError(type(item))
        if len(item) == 1:
            return SPECIAL_NAMES[item]
        if item[:2] == item[-2:] == '__':
            return self.special[item]
        return self.productions[item]

    def __setitem__(self, item, value):
        if not isinstance(item, str):
            raise TypeError(type(item))
        if item[:2] == item[-2:] == '__':
            self.special[item] = value
            return
        if len(item) == 1:
            raise ValueError(f"Grammar Rule name can not have length 1 {item!r}")
        self.productions[item].options.append(value)

    def to_dict(self):
        return dict(self.productions, **self.special)


class _GrammarMeta(type):
    @classmethod
    def __prepare__(mcs, name, bases, **kwargs):
        return GrammarDict({k: v for b in bases for k, v in b.__productions__.items()})

    def __new__(mcs, name, bases, namespace, **kwargs):
        t = super(_GrammarMeta, mcs).__new__(mcs, name, bases, namespace.to_dict())
        t.__productions__ = dict(namespace.productions)
        for v in t.__productions__.values():
            v.prepare()
        return t


class Grammar(metaclass=_GrammarMeta):
    pass
