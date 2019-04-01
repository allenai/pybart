import regex as re


class Token(object):
    def __init__(self, new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc):
        # format of CoNLL-U as described here: https://universaldependencies.org/format.html
        self._conllu_info = {"id": new_id, "form": form, "lemma": lemma, "upos": upos, "xpos": xpos,
                             "feats": feats, "head": head, "deprel": deprel, "deps": deps, "misc": misc}
        self._children_list = []
        self._new_deps = dict()
    
    def add_child(self, child):
        self._children_list.append(child)
    
    def remove_child(self, child):
        self._children_list.remove(child)
    
    def get_children(self):
        return self._children_list
    
    def get_conllu_info(self):
        return self._conllu_info.items()
    
    def get_conllu_field(self, field):
        return self._conllu_info[field]

    def is_root(self):
        # TODO - maybe we want to validate here (or/and somewhere else) that the root is an only parent
        return 0 in [parent.get_conllu_field('id') for parent in self.get_parents()]
    
    def get_parents(self):
        new_deps_pairs = self.get_new_relations()
        return [head for (head, edge) in new_deps_pairs]
    
    def get_new_relations(self, given_head=None):
        new_deps_pairs = []
        for head, edges in self._new_deps.items():
            # having more than one edge should really never happen
            for edge in edges:
                if not given_head or given_head == head:
                    new_deps_pairs.append((head, edge))
        
        return new_deps_pairs
    
    def match_rel(self, str_to_match, head):
        ret = []
        # having more than one edge should really never happen
        for edge in self._new_deps[head]:
            m = re.match(str_to_match, edge)
            if m:
                ret.append(edge)
        return ret
    
    def add_edge(self, rel, head):
        if head in self._new_deps:
            if rel in self._new_deps[head]:
                return
            self._new_deps[head] += [rel]
        else:
            self._new_deps[head] = [rel]
            head.add_child(self)
    
    def remove_edge(self, rel, head):
        if head in self._new_deps and rel in self._new_deps[head]:
            self._new_deps[head].remove(rel)
            if not self._new_deps[head]:
                self._new_deps.pop(head)
                head.remove_child(self)
    
    def remove_all_edges(self):
        for head, edge in self.get_new_relations():
            self.remove_edge(edge, head)
    
    def replace_edge(self, old_rel, new_rel, old_head, new_head):
        self.remove_edge(old_rel, old_head)
        self.add_edge(new_rel, new_head)
