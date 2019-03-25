import regex as re


class Token(object):
    def __init__(self, new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc):
        # format of CoNLL-U as described here: https://universaldependencies.org/format.html
        self._conllu_info = {"id": new_id, "form": form, "lemma": lemma, "upos": upos, "xpos": xpos,
                             "feats": feats, "head": head, "deprel": deprel, "deps": deps, "misc": misc}
        self._children_list = []
        self._new_deps = {head: [deprel]}
    
    def add_child(self, child):
        self._children_list.append(child)
    
    def remove_child(self, child):
        self._children_list.remove(child)
    
    def get_children(self):
        for child in self._children_list:
            yield child
    
    def get_conllu_info(self):
        return self._conllu_info.items()
    
    def get_conllu_field(self, field):
        return self._conllu_info[field]

    def is_root(self):
        return self._conllu_info['head'] == 0
    
    def get_parents_ids(self):
        new_deps_pairs = self.get_new_relations()
        return [head for (head, edge) in new_deps_pairs]
    
    def get_new_relations(self):
        new_deps_pairs = []
        for head, edges in self._new_deps.items():
            # having more than one edge should really never happen
            for edge in edges:
                new_deps_pairs.append((head, edge))
        
        return new_deps_pairs
    
    def match_rel(self, str_to_match):
        ret = []
        for head, edges in self._new_deps.items():
            # having more than one edge should really never happen
            for edge in edges:
                m = re.match(str_to_match, edge)
                if m:
                    ret.append(edge)
        return ret
    
    def add_edge(self, rel, head):
        head_id = head._conllu_info['id']
        if head_id in self._new_deps:
            if rel in self._new_deps[head_id]:
                return
            self._new_deps[head_id] += [rel]
        else:
            self._new_deps[head_id] = [rel]
            head.add_child(self)
    
    def remove_edge(self, rel, head):
        head_id = head._conllu_info['id']
        if head_id in self._new_deps and rel in self._new_deps[head_id]:
            self._new_deps[head_id].remove(rel)
            if not self._new_deps[head_id]:
                self._new_deps.pop(head_id)
                head.remove_child(self)
    
    def replace_edge(self, old_rel, new_rel, old_head, new_head):
        # old_head_id = old_head._conllu_info['id']
        # new_head_id = new_head._conllu_info['id']
        # if old_head_id not in self._new_deps or old_rel not in self._new_deps[old_head_id]:
        #     # TODO - decide if this is the correct behavior
        #     # self.add_edge(new_rel, new_head_id)
        #     raise ValueError("old relation dosn't exist in between the nodes")
        # TODO - decide what to do if no new_head_id, or if to have it optional
        # if not new_head_id:
        
        self.remove_edge(old_rel, old_head)
        self.add_edge(new_rel, new_head)
