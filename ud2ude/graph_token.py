import re


class Token(object):
    def __init__(self, new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc):
        # format of CoNLL-U as described here: https://universaldependencies.org/format.html
        self._conllu_info = {"id": new_id, "form": form, "lemma": lemma, "upos": upos, "xpos": xpos,
                             "feats": feats, "head": head, "deprel": deprel, "deps": deps, "misc": misc}
        self._children_list = []
        self._new_deps = dict()
        self._extra_info_edges = dict()
    
    def copy(self, new_id=None, form=None, lemma=None, upos=None, xpos=None, feats=None, head=None, deprel=None, deps=None, misc=None):
        new_id_copy, form_copy, lemma_copy, upos_copy, xpos_copy, feats_copy, head_copy, deprel_copy, deps_copy, misc_copy = self._conllu_info.values()
        return Token(new_id if new_id else new_id_copy,
                     form if form else form_copy,
                     lemma if lemma else lemma_copy,
                     upos if upos else upos_copy,
                     xpos if xpos else xpos_copy,
                     feats if feats else feats_copy,
                     head if head else head_copy,
                     deprel if deprel else deprel_copy,
                     deps if deps else deps_copy,
                     misc if misc else misc_copy)
    
    def add_child(self, child):
        self._children_list.append(child)
    
    def remove_child(self, child):
        self._children_list.remove(child)
    
    def get_children(self):
        return self._children_list
    
    def get_children_with_rels(self):
        return [(child, relation[1]) for child in self.get_children() for relation in child.get_new_relations(self)]
    
    def get_conllu_string(self):
        # for 'deps' field, we need to sort the new relations and then add them with '|' separation,
        # as required by the format.
        self._conllu_info["deps"] = "|".join([str(a.get_conllu_field('id')) + ":" + b for (a, b) in sorted(self.get_new_relations())])
        return "\t".join([str(v) for v in self._conllu_info.values()])
    
    def set_conllu_field(self, field, val):
        self._conllu_info[field] = val
    
    def get_conllu_field(self, field):
        return self._conllu_info[field]
    
    def is_root_node(self):
        return 0 == self.get_conllu_field('id')
    
    def is_root_rel(self):
        # TODO - maybe we want to validate here (or/and somewhere else) that a root is an only parent
        return 0 in [parent.get_conllu_field('id') for parent in self.get_parents()]
    
    def get_parents(self):
        return self._new_deps.keys()
    
    def get_extra_info_edges(self):
        return self._extra_info_edges
    
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
    
    def add_edge(self, rel, head, extra_info=None):
        if head in self._new_deps:
            if rel in self._new_deps[head]:
                return
            self._new_deps[head] += [rel]
        else:
            self._new_deps[head] = [rel]
            head.add_child(self)
        if extra_info:
            self._extra_info_edges[(head, rel)] = extra_info
    
    def remove_edge(self, rel, head):
        if head in self._new_deps and rel in self._new_deps[head]:
            self._new_deps[head].remove(rel)
            if not self._new_deps[head]:
                self._new_deps.pop(head)
                head.remove_child(self)
            if (head, rel) in self._extra_info_edges:
                self._extra_info_edges.pop((head, rel))
    
    def remove_all_edges(self):
        for head, edge in self.get_new_relations():
            self.remove_edge(edge, head)
    
    def replace_edge(self, old_rel, new_rel, old_head, new_head):
        self.remove_edge(old_rel, old_head)
        self.add_edge(new_rel, new_head)
    
    # operator overloading: less than
    def __lt__(self, other):
        return self.get_conllu_field('id') < other.get_conllu_field('id')
    
    def dist(self, other):
        return other.get_conllu_field('id') - self.get_conllu_field('id')
