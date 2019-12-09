import re
from collections import namedtuple

fields = ('name', 'gov', 'no_sons_of', 'form', 'xpos', 'follows', 'followed_by', 'diff', 'nested')
# TODO - when moving to python 3.7 replace to:
#   Restriction = namedtuple('Restriction', fields, defaults=(None,) * len(fields))
Restriction = namedtuple("Restriction", fields)
Restriction.__new__.__defaults__ = (None,) * len(Restriction._fields)


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
