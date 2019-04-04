import regex as re


class Restriction(object):
    def __init__(self, dictionary):
        self._dictionary = {"name": None, "gov": None, "no-gov": None, "diff": None,
                            "form": None, "xpos": None, "follows": None, "followed_by": None, "nested": None}
        self._dictionary.update(dictionary)
    
    def __setitem__(self, key, item):
        if key not in self._dictionary:
            raise KeyError("The key {} is not defined.".format(key))
        self._dictionary[key] = item
    
    def __getitem__(self, key):
        return self._dictionary[key]


# ----------------------------------------- matching functions ----------------------------------- #


def neighbors_restrictions(restriction, child, named_nodes):
    if restriction["follows"]:
        follows, _, _ = named_nodes[restriction["follows"]]
        if child.get_conllu_field('id') - 1 != follows.get_conllu_field('id'):
            return False
    
    if restriction["followed"]:
        followed, _, _ = named_nodes[restriction["followed"]][0]
        if child.get_conllu_field('id') + 1 != followed.get_conllu_field('id'):
            return False
    return True


def match_child(child, restriction, head):
    if restriction["form"]:
        if not re.match(restriction["form"], child.get_conllu_field('form')):
            return []
    
    if restriction["xpos"]:
        if not re.match(restriction["xpos"], child.get_conllu_field('xpos')):
            return []
    
    relations = [None]
    if restriction["gov"]:
        relations = child.match_rel(restriction["gov"], head)
        if len(relations) == 0:
            return []
    elif head:
        relations = [b for a, b in child.get_new_relations(head)]
    
    if restriction["no-gov"]:
        if False in [len(grandchild.match_rel(restriction["no-gov"], child)) == 0 for grandchild in
                     child.get_children()]:
            return []
    
    nested = []
    if restriction["nested"]:
        nested = match(
            child.get_children(),
            restriction["nested"],
            head=child)
        
        nested = [named_nodes for named_nodes in nested
                  if neighbors_restrictions(restriction, child, named_nodes)]
        
        if not nested:
            return []
    
    if restriction["name"]:
        ret = []
        for rel in relations:
            if nested:
                for d in nested:
                    d[restriction["name"]] = (child, head, rel)
                    ret.append(d)
            else:
                ret.append(dict({restriction["name"]: (child, head, rel)}))
    else:
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
