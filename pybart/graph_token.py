from dataclasses import dataclass, field


@dataclass
class TokenId:
    major: int
    minor: int = 0
    token_str: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'token_str', f"{self.major}.{self.minor}" if self.minor else f"{self.major}")

    def __str__(self):
        return self.token_str

    def __lt__(self, other):
        return self.major < other.major or (self.major == other.major and self.minor < other.minor)

@dataclass
class Label:
    base: str
    eud: str = None
    src: str = None
    src_type: str = None
    phrase: str = None
    uncertain: bool = False
    iid: int = None

    def to_str(self, remove_enhanced_extra_info, remove_bart_extra_info):
        eud = ""
        if self.eud is not None:
            if not remove_enhanced_extra_info:
                eud = ":" + self.eud

        bart = ""
        if self.src is not None:
            if not remove_bart_extra_info:
                iid_str = "" if self.iid is None else "#" + str(self.iid)
                dep_args = ", ".join(x for x in filter(None, [self.src_type, self.phrase, "UNC" if self.uncertain else None]))
                bart = "@" + self.src + "(" + dep_args + ")" + iid_str

        return self.base + eud + bart

    # operator overloading: less than
    def __lt__(self, other):
        return self.to_str(False, False) < other.to_str(False, False)


class Token:
    def __init__(self, new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc):
        # format of CoNLL-U as described here: https://universaldependencies.org/format.html
        self._conllu_info = {"id": new_id, "form": form, "lemma": lemma, "upos": upos, "xpos": xpos,
                             "feats": feats, "head": head, "deprel": deprel, "deps": deps, "misc": misc}
        self._children_list = []
        self._new_deps = dict()

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
        return [(child, list(child.get_new_relations(self))[0][1]) for child in self.get_children()]

    def get_conllu_string(self, remove_enhanced_extra_info, remove_bart_extra_info):
        # for 'deps' field, we need to sort the new relations and then add them with '|' separation,
        # as required by the format.
        sorted_ = sorted((h, sorted(rels)) for h, rels in self.get_new_relations())
        self._conllu_info["deps"] = "|".join([str(a.get_conllu_field('id')) + ":" + bb.to_str(remove_enhanced_extra_info, remove_bart_extra_info) for (a, b) in sorted_ for bb in b])
        return "\t".join([str(v) for v in self._conllu_info.values()])
    
    def set_conllu_field(self, field, val):
        self._conllu_info[field] = val
    
    def get_conllu_field(self, field):
        return self._conllu_info[field]

    def get_parents(self):
        return self._new_deps.keys()
    
    def get_new_relations(self, given_head=None):
        if given_head:
            if given_head in self._new_deps:
                return [(given_head, self._new_deps[given_head])]
            else:
                return dict().items()
        else:
            return self._new_deps.items()

    def add_edge(self, rel, head):
        assert isinstance(rel, Label)
        if head in self._new_deps:
            if rel in self._new_deps[head]:
                return
            self._new_deps[head] += [rel]
        else:
            self._new_deps[head] = [rel]
            head.add_child(self)
    
    def remove_edge(self, rel, head):
        assert isinstance(rel, Label)
        if head in self._new_deps and rel in self._new_deps[head]:
            self._new_deps[head].remove(rel)
            if not self._new_deps[head]:
                self._new_deps.pop(head)
                head.remove_child(self)
    
    def remove_all_edges(self):
        _ = [self.remove_edge(edge, head) for head, edges in list(self.get_new_relations()) for edge in edges]
    
    def replace_edge(self, old_rel, new_rel, old_head, new_head):
        self.remove_edge(old_rel, old_head)
        self.add_edge(new_rel, new_head)
    
    # operator overloading: less than
    def __lt__(self, other):
        return self.get_conllu_field('id') < other.get_conllu_field('id')


def add_basic_edges(sentence):
    """Purpose: adds each basic deprel relation and the relevant father to its son.

    Args:
        (dict) The parsed sentence.
    """
    for (cur_id, token) in enumerate(sentence):
        # add the relation
        head = token.get_conllu_field('head')
        if head is not None:
            sentence[cur_id].add_edge(Label(token.get_conllu_field('deprel')), sentence[head.major - 1])
