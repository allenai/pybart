import regex as re
from collections import namedtuple

fields = ('name', 'gov', 'no_sons_of', 'form', 'xpos', 'follows', 'followed_by', 'diff', 'nested')
# TODO - when moving to python 3.7 replace to:
#   Restriction = namedtuple('Restriction', fields, defaults=(None,) * len(fields))
Restriction = namedtuple("Restriction", fields)
Restriction.__new__.__defaults__ = (None,) * len(Restriction._fields)


# ----------------------------------------- matching functions ----------------------------------- #


def named_nodes_restrictions(restriction, child, named_nodes):
    if restriction.follows:
        follows, _, _ = named_nodes[restriction.follows]
        if child.get_conllu_field('id') - 1 != follows.get_conllu_field('id'):
            return False
    
    if restriction.followed:
        followed, _, _ = named_nodes[restriction.followed_by]
        if child.get_conllu_field('id') + 1 != followed.get_conllu_field('id'):
            return False
    
    if restriction.diff:
        diff, _, _ = named_nodes[restriction.followed_by]
        if child == diff:
            return False
    
    return True


def check_nested_restriction(child, restriction):
    nested = match(
        child.get_children(),
        restriction.nested,
        head=child)
    
    return [named_nodes for named_nodes in nested if
            named_nodes_restrictions(restriction, child, named_nodes)]


def match_child(child, restriction, head):
    if restriction.form:
        if not re.match(restriction.form, child.get_conllu_field('form')):
            return []
    
    if restriction.xpos:
        if not re.match(restriction.xpos, child.get_conllu_field('xpos')):
            return []
    
    # if no head (first level words)
    relations = [None]
    if restriction.gov:
        relations = child.match_rel(restriction.gov, head)
        if len(relations) == 0:
            return []
    elif head:
        relations = [b for a, b in child.get_new_relations(head)]
    
    if restriction.no_sons_of:
        if False in [len(grandchild.match_rel(restriction.no_sons_of, child)) == 0 for grandchild in
                     child.get_children()]:
            return []
    
    nested = []
    if restriction.nested:
        nested = check_nested_restriction(child, restriction)
        if not nested:
            return []
    
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
    for child in children:
        ret += match_child(child, restriction, head)
    
    return ret


def match_rl(children, restriction_list, head):
    ret = []
    rest_rets = []
    for restriction in restriction_list:
        rest_ret = match_rest(children, restriction, head)
        
        # if one restriction was violated, return empty list.
        if not rest_ret:
            return []
        
        rest_rets.append(rest_ret)
    
    # every new rest_ret should be merged to any previous rest_ret
    # we do this here because we are lazy -
    # we don't want to do this work if one restriction was violated.
    for rest_ret in rest_rets:
        ret = rest_ret if not ret else \
            [{**ns_ret, **ns_rest_ret} for ns_rest_ret in rest_ret for ns_ret in ret]
    
    return ret
    

def match(children, restriction_lists, head=None):
    for restriction_list in restriction_lists:
        ret = match_rl(children, restriction_list, head)
        if ret:
            return ret
    return []
