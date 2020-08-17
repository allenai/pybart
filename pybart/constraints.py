from dataclasses import dataclass, field
from typing import Sequence, Set
from enum import Enum


class FieldNames(Enum):
    WORD = 0
    LEMMA = 1
    TAG = 2
    ENTITY = 3


@dataclass(frozen=True)
class Field:
    field: FieldNames
    value: Sequence[str]  # match of one of the strings in a list


@dataclass(frozen=True)
class Label():
    pass


@dataclass(frozen=True)
class HasLabelFromList(Label):
    # has at least one edge with value
    value: Sequence[str]


@dataclass(frozen=True)
class HasNoLabel(Label):
    # does not have edge with value
    value: str


@dataclass(frozen=True)
class Token:
    id: str  # id/name for the token
    capture: bool = True
    spec: Sequence[Field] = field(default_factory=list)
    optional: bool = False  # is this an optional constraint or required
    incoming_edges: Sequence[Label] = field(default_factory=list)
    outgoing_edges: Sequence[Label] = field(default_factory=list)
    is_root: bool = None  # optional field, if set, then check if this is/n't (depending on the bool value) the root


@dataclass(frozen=True)
class Edge:
    child: str
    parent: str
    label: Sequence[Label]


@dataclass(frozen=True)
class Distance:
    token1: str
    token2: str
    distance: int


@dataclass(frozen=True)
class ExactDistance(Distance):
    # 0 means no words in between... 3 means exactly words are allowed in between, etc.
    pass


@dataclass(frozen=True)
class UptoDistance(Distance):
    # 0 means no words in between... 3 means up to three words are allowed in between, etc.
    #   so infinity is like up to any number of words in between (which means only the order of the arguments matters).
    pass


@dataclass(frozen=True)
class TokenTuple:  # the words of the nodes must match
    tuple_set: Set[str]  # each str is word pair separated by _


@dataclass(frozen=True)
class TokenPair(TokenTuple):  # the words of the nodes must match
    token1: str
    token2: str
    in_set: bool = True  # should or shouldn't match


@dataclass(frozen=True)
class TokenTriplet(TokenTuple):  # the words of the nodes must/n't match
    token1: str
    token2: str
    token3: str
    in_set: bool = True  # should or shouldn't match


@dataclass(frozen=True)
class Full:
    tokens: Sequence[Token] = field(default_factory=list)
    edges: Sequence[Edge] = field(default_factory=list)
    distances: Sequence[Distance] = field(default_factory=list)
    concats: Sequence[TokenTuple] = field(default_factory=list)


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
