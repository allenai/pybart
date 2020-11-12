from dataclasses import dataclass, field
from typing import Sequence, Set, List, Optional, Callable, Any
from enum import Enum
from math import inf
from abc import ABC, abstractmethod


class FieldNames(Enum):
    WORD = 0
    LEMMA = 1
    TAG = 2
    ENTITY = 3


@dataclass(frozen=True)
class Field:
    field: FieldNames
    value: Sequence[str]  # match of one of the strings in a list
    in_sequence: bool = True

    def __post_init__(self):
        # validate value's value specifically because str is converted to list and this is hard to debug
        if not isinstance(self.value, list):
            raise ValueError(f"Expected <class 'list'> got {type(self.value)}")
        object.__setattr__(self, 'value', [v.lower() for v in self.value])

    def satisfied(self, context: Any, get_content_by_field: Callable[[Any, FieldNames], str]) -> bool:
        return not ((get_content_by_field(context, self.field).lower() in self.value) ^ self.in_sequence)


@dataclass(frozen=True)
class LabelPresence(ABC):
    @abstractmethod
    def satisfied(self, actual_labels: List[str]) -> Set[str]:
        pass


@dataclass(frozen=True)
class HasLabelFromList(LabelPresence):
    # has at least one edge with value
    value: Sequence[str]
    is_regex: bool = field(default=False, init=False)

    def __post_init__(self):
        # validate value's value specifically because str is converted to list and this is hard to debug
        if not isinstance(self.value, list):
            raise ValueError(f"Expected <class 'list'> got {type(self.value)}")
        if len(self.value) == 1 and self.value[0].startswith('/') and self.value[0].endswith('/'):
            object.__setattr__(self, 'is_regex', True)

    def satisfied(self, actual_labels: List[str]) -> Optional[Set[str]]:
        # at least one of the constraint strings should match, so return False only if none of them did.
        if self.is_regex:
            return set(actual_labels)

        # for each edged label, check if the label matches the constraint, and store it if it does,
        #   because it is a positive search (that is at least one label should match)
        current_successfully_matched = [v for v in self.value if v in actual_labels]

        if len(current_successfully_matched) == 0:
            return None
        return set(current_successfully_matched)


@dataclass(frozen=True)
class HasNoLabel(LabelPresence):
    # does not have edge with value
    value: str

    def satisfied(self, actual_labels: List[str]) -> Optional[Set[str]]:
        # for each edged label, check if the label matches the constraint, and fail if it does,
        #   because it is a negative search (that is non of the labels should match)
        if self.value in actual_labels:
            return None
        return set()


@dataclass(frozen=True)
class Token:
    id: str  # id/name for the token
    capture: bool = True
    spec: Sequence[Field] = field(default_factory=list)
    optional: bool = False  # is this an optional constraint or required
    incoming_edges: Sequence[LabelPresence] = field(default_factory=list)
    outgoing_edges: Sequence[LabelPresence] = field(default_factory=list)
    no_children: bool = False  # should this token have no children or can it
    is_root: bool = False  # should this token have no parents (i.e. it is the root) or can it


@dataclass(frozen=True)
class Edge:
    child: str
    parent: str
    label: Sequence[LabelPresence]
    optional: bool = field(init=False, default=False)

    def adjust_optionality(self, is_any_opt):
        object.__setattr__(self, 'optional', is_any_opt)


@dataclass(frozen=True)
class Distance(ABC):
    token1: str
    token2: str
    distance: int

    @abstractmethod
    def satisfied(self, calculated_distance: int) -> bool:
        pass


@dataclass(frozen=True)
class ExactDistance(Distance):
    # 0 means no words in between... 3 means exactly words are allowed in between, etc.
    def __post_init__(self):
        if self.distance < 0:
            raise ValueError("Exact distance can't be negative")
        elif self.distance == inf:
            raise ValueError("Exact distance can't be infinity")

    def satisfied(self, calculated_distance: int) -> bool:
        return self.distance == calculated_distance


@dataclass(frozen=True)
class UptoDistance(Distance):
    # 0 means no words in between... 3 means up to three words are allowed in between, etc.
    #   so infinity is like up to any number of words in between (which means only the order of the arguments matters).
    def __post_init__(self):
        if self.distance < 0:
            raise ValueError("'up-to' distance can't be negative")

    def satisfied(self, calculated_distance: int) -> bool:
        return 0 <= calculated_distance <= self.distance


@dataclass(frozen=True)
class TokenTuple(ABC):  # the words of the nodes must match
    tuple_set: Set[str]  # each str is word pair separated by _

    def __post_init__(self):
        # validate value's value specifically because str is converted to list and this is hard to debug
        if not isinstance(self.tuple_set, set):
            raise ValueError(f"Expected <class 'set'> got {type(self.tuple_set)}")

    # Note - a bit ugly but best workaround for defining in_set in the parent level, as it has a default value,
    #   and can't be declared before the children's Tokens, but also not sufficient to declare only at children,
    #   as then we would need to have a copy of satisfied for each child
    @property
    def in_set(self):
        raise NotImplementedError

    @abstractmethod
    def get_token_names(self) -> Sequence[str]:
        pass

    def satisfied(self, optional_tuple: str) -> bool:
        return not ((optional_tuple in self.tuple_set) ^ self.in_set)


@dataclass(frozen=True)
class TokenPair(TokenTuple):  # the words of the nodes must match
    token1: str
    token2: str
    in_set: bool = True  # should or shouldn't match

    def get_token_names(self) -> Sequence[str]:
        return [self.token1, self.token2]


@dataclass(frozen=True)
class TokenTriplet(TokenTuple):  # the words of the nodes must/n't match
    token1: str
    token2: str
    token3: str
    in_set: bool = True  # should or shouldn't match

    def get_token_names(self) -> Sequence[str]:
        return [self.token1, self.token2, self.token3]


@dataclass(frozen=True)
class Full:
    tokens: Sequence[Token] = field(default_factory=list)
    edges: Sequence[Edge] = field(default_factory=list)
    distances: Sequence[Distance] = field(default_factory=list)
    concats: Sequence[TokenTuple] = field(default_factory=list)
    
    def __post_init__(self):
        # check for no repetition
        names = [tok.id for tok in self.tokens]
        names_set = set(names)
        if len(names) != len(names_set):
            raise ValueError("used same name twice")
        
        # validate for using only names defined in tokens
        used_names = set()
        [used_names.update({edge.child, edge.parent}) for edge in self.edges]
        [used_names.update({dist.token1, dist.token2}) for dist in self.distances]
        for concat in self.concats:
            if isinstance(concat, TokenPair):
                used_names.update({concat.token1, concat.token2})
            elif isinstance(concat, TokenTriplet):
                used_names.update({concat.token1, concat.token2, concat.token3})
        
        if len(used_names.difference(names_set)) != 0:
            raise ValueError("used undefined names")

        # validate no_children doesn't clash with edges or label constraints
        for edge in self.edges:
            if any(tok.no_children for tok in self.tokens if tok.id == edge.parent):
                raise ValueError(
                    "Found an edge constraint with a parent token that already has a no_children constraint")
            if any(tok.is_root for tok in self.tokens if tok.id == edge.child):
                raise ValueError(
                    "Found an edge constraint with a child token that already has a is_root constraint")
        for tok in self.tokens:
            if (tok.no_children and tok.outgoing_edges) or (tok.is_root and tok.incoming_edges):
                raise ValueError(
                    "Found a token with a no_children/is_root constraint and outgoing_edges/incoming_edges constraint")

        for edge in self.edges:
            is_child_opt = any(tok.optional for tok in self.tokens if tok.id == edge.child)
            is_parent_opt = any(tok.optional for tok in self.tokens if tok.id == edge.parent)
            edge.adjust_optionality(is_child_opt or is_parent_opt)


# usage examples:
#
# for three-word-preposition processing
# Full(
#     tokens=[
#         Token(id="w1", outgoing_edges=[HasNoLabel("/.*/")]),
#         Token(id="w2"),
#         Token(id="w3", outgoing_edges=[HasNoLabel("/.*/")]),
#         Token(id="proxy")],
#     edges=[
#         Edge(child="proxy", parent="w2", label=[HasLabelFromList(["/nmod|acl|advcl).*/"])]),
#         Edge(child="w1", parent="w2", label=[HasLabelFromList(["case"])]),
#         Edge(child="w3", parent="proxy", label=[HasLabelFromList(["case", "mark"])])
#     ],
#     distances=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "w3", distance=0)],
#     concats=[TokenTriplet(three_word_preps, "w1", "w2", "w3")]
# )
#
#
# for "acl propagation" (type1)
# Full(
#     tokens=[
#         Token(id="verb", spec=[Field(FieldNames.TAG, ["/(VB.?)/"])]),
#         Token(id="subj"),
#         Token(id="proxy"),
#         Token(id="acl", outgoing_edges=[HasNoLabel("/.subj.*/")]),
#         Token(id="to", spec=[Field(FieldNames.TAG, ["TO"])])],
#     edges=[
#         Edge(child="subj", parent="verb", label=[HasLabelFromList(["/.subj.*/"])]),
#         Edge(child="proxy", parent="verb", label=[HasLabelFromList(["/.*/"])]),
#         Edge(child="acl", parent="proxy", label=[HasLabelFromList(["/acl(?!:relcl)/"])]),
#         Edge(child="to", parent="acl", label=[HasLabelFromList(["mark"])])
#     ],
# )
#
#
# for passive alternation
# Full(
#     tokens=[
#         Token(id="predicate"),
#         Token(id="subjpass"),
#         Token(id="agent", optional=True),
#         Token(id="by", optional=True, spec=[Field(FieldNames.WORD, ["^(?i:by)$"])])],
#     edges=[
#         Edge(child="subjpass", parent="predicate", label=[HasLabelFromList(["/.subjpass/"])]),
#         Edge(child="agent", parent="predicate", label=[HasLabelFromList(["/^(nmod(:agent)?)$/"])]),
#         Edge(child="by", parent="agent", label=[HasLabelFromList(["case"])]),
#         Edge(child="subjpass", parent="predicate", label=[HasNoLabel(".obj")])
#     ]
# )
