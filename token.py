class Token(object):
    def __init__(self, new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc):
        # format of CoNLL-U as described here: https://universaldependencies.org/format.html
        self._conllu_info = {"new_id": new_id, "form": form, "lemma": lemma, "upos": upos, "xpos": xpos,
                             "feats": feats, "head": head, "deprel": deprel, "deps": deps, "misc": misc}
        self._children_list = []
        self._parents_list = []
        self._new_deps = {head: [deprel]}
        self._is_new_deps_changed = False
    
    def add_child(self, child):
        self._children_list.append(child)
    
    def remove_child(self, child):
        self._children_list.remove(child)
    
    def get_children(self):
        for child in self._children_list:
            yield child
    
    def add_parent(self, parent):
        self._parents_list.append(parent)
    
    def remove_parent(self, parent):
        self._parents_list.remove(parent)
    
    def get_parents(self):
        for parent in self._parents_list:
            yield parent
    
    def get_conllu_info(self):
        return self._conllu_info.items()
    
    def is_root(self):
        return self._conllu_info['head'] == 0
    
    def is_new_deps_changed(self):
        return self._is_new_deps_changed
    
    def get_new_deps_pairs(self):
        new_deps_pairs = []
        for k, v in self._new_deps:
            for v_tag in v:
                new_deps_pairs.append((k, v_tag))
        return self._new_deps
    
    def add_new_dep(self, head, rel):
        self._is_new_deps_changed = True
        self._new_deps[head] = self._new_deps['head'] + [rel] if head in self._new_deps else [rel]
    
    def remove_new_dep(self, head, rel):
        self._is_new_deps_changed = True
        self._new_deps[head].pop(rel)
        if not self._new_deps[head]:
            self._new_deps.pop(head)
    
    def replace_new_dep(self, head, rel_to_add, rel_to_remove):
        self.add_new_dep(head, rel_to_add)
        self.remove_new_dep(head, rel_to_remove)
