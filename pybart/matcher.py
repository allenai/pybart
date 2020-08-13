import re
from dataclasses import dataclass, field
from typing import Dict, List, Union, Set
from enum import Enum

from collections import namedtuple

fields = ('name', 'gov', 'no_sons_of', 'form', 'lemma', 'xpos', 'follows', 'followed_by', 'diff', 'nested')
Restriction = namedtuple('Restriction', fields, defaults=(None,) * len(fields))


# NOTE: same node cannot take two roles in structure.


class FieldNames(Enum):
    WORD = 0
    LEMMA = 1
    TAG = 2
    ENTITY = 3


class FieldTypes(Enum):
    EXACT = 0
    REGEX = 1
    LIST = 2


@dataclass
class FieldConstraint:
    field: FieldNames
    type: FieldTypes
    value: Union[str, List[str]]  # either an exact/regex string or a match of one of the strings in a list


@dataclass
class LabelConstraint:
    # has at least one edge of type (this covers the case of “has one edge of type” (if we give a list of length 1) and the case of OR. while the case of AND is covered by the incoming_edges/outgoing_edges in the TokenConstraint)
    has_edge_from_list: List[str] = field(default_factory=list())
    # does not have edge type (this covers the case of validating none of the edges has the following edge type. The AND case is covered by the incoming_edges/outgoing_edges in the TokenConstraint, and the OR case is not covered because it doesn’t make much sense)
    no_edge: str = None


@dataclass
class TokenConstraint:
    id: int  # each token is indexed by a number
    spec: List[FieldConstraint] = field(default_factory=list())
    optional: bool = False  # is this an optional constraint or required
    incoming_edges: List[LabelConstraint] = field(default_factory=list())
    outgoing_edges: List[LabelConstraint] = field(default_factory=list())
    is_root: bool = None  # optional field, if set, then check if this is/n't (depending on the bool value) the root


@dataclass
class EdgeConstraint:
    target: int
    source: int
    label: List[str]  # TODO - str ot regex? or a class for Label, with basic/EUD/BART parts, which we will define later on
    # whether at least one match is enough or should be satisfied against all edges between the two nodes.
    #   This is for a case of negative lookup (regex-wise) in which we need to satisfy it against all edges (between the two nodes).
    negative: bool = False  # TODO - must be False for now (to discuss semantics of True later: probably applies after structure is set.)


@dataclass
class ExactLinearConstraint:
    tok1: int
    tok2: int
    distance: int  # -1 is not valid, 0 means no words in between, 3 means exactly words are allowed in between, etc.


@dataclass
class UptoLinearConstraint:
    tok1: int
    tok2: int
    # -1 means only order matters (like up to any number of words in between), 0 means no words in between,
    #   3 means up to three words are allowed in between, etc.
    distance: int


@dataclass
class TokenPairConstraint:  # the words of the nodes must match
    token1: int
    token2: int
    str_ids: Set[str]  # this str is word separated by _
    in_set: bool = True # should or shouldn't match


@dataclass
class TokenTripletConstraint:  # the words of the nodes must/n't match
    token1: int
    token2: int
    token3: int
    str_ids: Set[str]  # this str is word separated by _
    in_set: bool = True  # should or shouldn't match


@dataclass
class FullConstraint:
    names: Dict[int, str] = field(default_factory=dict())
    tokens: List[TokenConstraint] = field(default_factory=list())
    edges: List[EdgeConstraint] = field(default_factory=list())
    exact_linear: List[ExactLinearConstraint] = field(default_factory=list())
    upto_linear: List[UptoLinearConstraint] = field(default_factory=list())
    concat_pairs: List[TokenPairConstraint] = field(default_factory=list())
    concat_triplets: List[TokenTripletConstraint] = field(default_factory=list())

# usage examples:
#
# for three-word-preposition processing
# restriction = FullConstraint(
#     names={1: "w1", 2: "w2", 3: "w3", 4: "w2_proxy_w3"},
#     tokens=[
#         TokenConstraint(id=1, outgoing_edges=[LabelConstraint(no_edge=".*")]),
#         TokenConstraint(id=2),
#         TokenConstraint(id=3, outgoing_edges=[LabelConstraint(no_edge=".*")]),
#         TokenConstraint(id=4)],
#     edges=[
#         EdgeConstraint(target=4, source=2, label=["(nmod|acl|advcl).*"]),
#         EdgeConstraint(target=1, source=2, label=["case"]),
#         EdgeConstraint(target=3, source=4, label=["case|mark"])
#     ],
#     exact_linear=[ExactLinearConstraint(1, 2, distance=0), ExactLinearConstraint(2, 3, distance=0)],
#     concat_triplets=[TokenTripletConstraint(1, 2, 3, three_word_preps)]
# )
#
#
# for "acl propagation" (type1)
# FullConstraint(
#     names={1: "verb", 2: "subj", 3: "middle_man", 4: "acl", 5: "to"},
#     tokens=[
#         TokenConstraint(id=1, spec=[FieldConstraint(FieldNames.TAG, FieldTypes.REGEX, "(VB.?)")]),
#         TokenConstraint(id=2),
#         TokenConstraint(id=3),
#         TokenConstraint(id=4, outgoing_edges=[LabelConstraint(no_edge=".subj.*")]),
#         TokenConstraint(id=5, spec=[FieldConstraint(FieldNames.TAG, FieldTypes.EXACT, "TO")])],
#     edges=[
#         EdgeConstraint(target=2, source=1, label=[".subj.*"]),
#         EdgeConstraint(target=3, source=1, label=[".*"]),
#         EdgeConstraint(target=4, source=3, label=["acl(?!:relcl)"]),
#         EdgeConstraint(target=5, source=4, label=["mark"])
#     ],
# )
#


# ----------------------------------------- matching functions ----------------------------------- #


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
