import re
from collections import namedtuple
from dataclasses import dataclass, field
from typing import Sequence, Set
from enum import Enum

# TODO - old matcher's restriction, should be removed
fields = ('name', 'gov', 'no_sons_of', 'form', 'lemma', 'xpos', 'follows', 'followed_by', 'diff', 'nested')
Restriction = namedtuple('Restriction', fields, defaults=(None,) * len(fields))


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
class ExactDistance:
    token1: str
    token2: str
    distance: int  # 0 means no words in between... 3 means exactly words are allowed in between, etc.


@dataclass(frozen=True)
class UptoDistance:
    token1: str
    token2: str
    # 0 means no words in between... 3 means up to three words are allowed in between, etc.
    #   so infinity is like up to any number of words in between (which means only the order of the arguments matters).
    distance: int


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
    distances: Sequence[TokenTuple] = field(default_factory=list)
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
#         Edge(child="proxy", parent="w2", label=[HasLabelFromList([/"nmod|acl|advcl).*"//]),
#         Edge(child="w1", parent="w2", label=[HasLabelFromList(["case"])]),
#         Edge(child="w3", parent="proxy", label=[HasLabelFromList(["case", "mark"])])
#     ],
#     exact_linear=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "w3", distance=0)],
#     concat_triplets=[TokenTriplet(three_word_preps, "w1", "w2", "w3")]
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
#         Edge(child="by", parent="agent", label=[HasLabelFromList(["case"])])
#         Edge(child="subjpass", parent="predicate", label=[HasNoEdge(".obj")])
#     ]
# )


# ----------------------------------------- matching functions ----------------------------------- #
# TODO - when writing the new matcher: same node cannot take two roles in structure.


def named_nodes_restrictions(restriction, named_nodes):
    if restriction.name:
        child, _, _ = named_nodes[restriction.name]
    else:
        return True
    
    if restriction.follows:
        follows, _, _ = named_nodes[restriction.follows]
        if child.get_conllu_field('id') - 1 != follows.get_conllu_field('id'):
            return False
    
    if restriction.followed_by:
        followed, _, _ = named_nodes[restriction.followed_by]
        if child.get_conllu_field('id') + 1 != followed.get_conllu_field('id'):
            return False
    
    if restriction.diff:
        diff, _, _ = named_nodes[restriction.diff]
        if child == diff:
            return False
    
    return True


def match_child(child, restriction, head):
    if restriction.form:
        if child.is_root_node() or not re.match(restriction.form, child.get_conllu_field('form')):
            return
    
    if restriction.lemma:
        if child.is_root_node() or not re.match(restriction.lemma, child.get_conllu_field('lemma')):
            return
    
    if restriction.xpos:
        if child.is_root_node() or not re.match(restriction.xpos, child.get_conllu_field('xpos')):
            return
    
    # if no head (first level words)
    relations = [None]
    if restriction.gov:
        relations = child.match_rel(restriction.gov, head)
        if len(relations) == 0:
            return
    elif head:
        relations = [b for a, b in child.get_new_relations(head)]
    
    if restriction.no_sons_of:
        if False in [len(grandchild.match_rel(restriction.no_sons_of, child)) == 0 for grandchild in
                     child.get_children()]:
            return
    
    nested = []
    if restriction.nested:
        nested = match(child.get_children(), restriction.nested, child)
        if nested is None:
            return
    
    if restriction.name:
        ret = []
        for rel in relations:
            if nested:
                for d in nested:
                    d[restriction.name] = (child, head, rel)
                    ret.append(d)
            else:
                ret.append(dict({restriction.name: (child, head, rel)}))
        return ret
    
    return nested
    

def match_rest(children, restriction, head):
    ret = []
    restriction_satisfied = False
    for child in children:
        child_ret = match_child(child, restriction, head)
        
        # we check to see for None because empty list is a legit return value
        if child_ret is None:
            continue
        else:
            restriction_satisfied = True
        ret += child_ret
    
    if not restriction_satisfied:
        return None
    return ret


def match_rl(children, restriction_list, head):
    ret = []
    for restriction in restriction_list:
        rest_ret = match_rest(children, restriction, head)
        
        # if one restriction was violated, return empty list.
        if rest_ret is None:
            return None
        
        # every new rest_ret should be merged to any previous rest_ret
        ret = rest_ret if not ret else \
            [{**ns_ret, **ns_rest_ret} for ns_rest_ret in rest_ret for ns_ret in ret]
        # fix ret in case we have two identical name_spaces
        ret = [r for i, r in enumerate(ret) if r not in ret[i + 1:]]
        
        ret_was_empty_beforehand = False
        if not ret:
            ret_was_empty_beforehand = True
        for named_nodes in ret:
            # this is done here because we want to check cross restrictions
            # TODO - move the following information from here:
            #   rules regarding the usage of non graph restrictions (follows, followed_by, diff):
            #   1. must be after sibling rest's that they refer to
            #       or in the outer rest of a nested that they refer to
            #   2. must have names for themselves
            if not named_nodes_restrictions(restriction, named_nodes):
                ret.remove(named_nodes)
        if (not ret) and (not ret_was_empty_beforehand):
            return None
    
    return ret
    

def match(children, restriction_lists, head=None):
    for restriction_list in restriction_lists:
        ret = match_rl(children, restriction_list, head)
        if ret is not None:
            return ret
    return
