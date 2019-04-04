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

def match(children, restriction_lists, head=None):
    ret = []
    for restriction_list in restriction_lists:
        one_restriction_violated = False
        for restriction in restriction_list:
            restriction_matched = False
            for child in children:
                if restriction["form"]:
                    if not re.match(restriction["form"], child.get_conllu_field('form')):
                        continue
                
                if restriction["xpos"]:
                    if not re.match(restriction["xpos"], child.get_conllu_field('xpos')):
                        continue
                
                relations = [None]
                if restriction["gov"]:
                    relations = child.match_rel(restriction["gov"], head)
                    if len(relations) == 0:
                        continue
                elif head:
                    relations = [b for a, b in child.get_new_relations(head)]
                
                if restriction["no-gov"]:
                    if False in [len(grandchild.match_rel(restriction["no-gov"], child)) == 0 for grandchild in
                                 child.get_children()]:
                        continue
                
                nested = []
                if restriction["nested"]:
                    nested = match(
                        child.get_children(),
                        restriction["nested"],
                        head=child)
                    
                    nested = [named_nodes for named_nodes in nested
                              if neighbors_restrictions(restriction, child, named_nodes)]
                    
                    if not nested:
                        continue
                
                if restriction["name"]:
                    for rel in relations:
                        if nested:
                            for d in nested:
                                d[restriction["name"]] = (child, head, rel)
                                ret.append(d)
                        else:
                            ret.append(dict({restriction["name"]: (child, head, rel)}))
                else:
                    ret = nested
                restriction_matched = True
            
            if not restriction_matched:
                one_restriction_violated = True
                break
        
        if not one_restriction_violated:
            return ret
    
    return ret
