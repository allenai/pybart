import re
from dataclasses import dataclass
from typing import Tuple, List, Union
from enum import Enum


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
class InoutConstraint:
    in_or_out: bool  # consider the incoming or ingoing edges
    w_o: bool  # with/out: should at least one of in/out edges have the label (w=with), or should none of the in/out edge have the label (o=without)
    label: str  # the label to match. TODO: should default be regex? maybe consider Label class (see edge notes)


@dataclass
class TokenConstraint:
    id: int  # each token is indexed by a number
    optional: bool  # is this an optional constraint or required
    spec: List[FieldConstraint]
    is_root: bool = None  # optional field, if set, then check if this is/n't (depending on the bool value) the root
    inout_filter: List[InoutConstraint] = None  # filter this token according to his incoming/outgoing edges


@dataclass
class EdgeConstraint:
    target: int
    source: int
    label: str  # or a class for Label, with basic/EUD/BART parts, which we will define later on
    # whether at least one match is enough or should be satisfied against all edges between the two nodes.
    #   This is for a case of negative lookup (regex-wise) in which we need to satisfy it against all edges (between the two nodes).
    negative: bool = False


@dataclass
class LinearConstraint:
    tok1: int
    tok2: int
    slop: int # -1 means only order matters, 0 means no words in between, etc.


@dataclass
class StructuralConstraint:
    # the concatenation of words from the tokens specified by their IDs, should/n't (depending on the boolean) appear in the given list of strings
    concat_in_list: Tuple[List[int], List[str], bool] = None
    
    linear: List[LinearConstraint] = None
    
    diff: List[Tuple[int, int]] = None  # list of pairs of token ids. each pair states that these two tokens should be different nodes from each other.
    # for each token id return the entire cluster of tokens that satisfy that node constraint,
    #   instead of splitting it into different match-sets.
    all: List[int] = None
    # opt_group: List[List[int]] = None  # problematic for now, maybe could be solved by splitting a restriction
    

@dataclass
class FullConstraint:
    tokens: List[TokenConstraint]
    edges: List[EdgeConstraint]
    structural: StructuralConstraint


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
