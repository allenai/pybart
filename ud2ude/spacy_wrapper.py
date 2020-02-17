from spacy.tokens import Doc, Token as SpacyToken
from spacy import attrs
import numpy as np

from .graph_token import Token, add_basic_edges, parse_bart_label

# this is here because it needs to happen only once (per import)
SpacyToken.set_extension("parent_list", default=[])


def parse_spacy_doc(doc):
    sentence = dict()
    
    for i, tok in enumerate(doc):
        # add current token to current sentence
        sentence[tok.i + 1] = Token(
            tok.i + 1, tok.text, tok.lemma_, tok.pos_, tok.tag_, "_", (tok.head.i + 1) if tok.head.i != i else 0,
            tok.dep_.lower(), "_", "_")
    
    # add root
    sentence[0] = Token(0, None, None, None, None, None, None, None, None, None)
    
    # after parsing entire sentence, add basic deprel edges,
    # and add sentence to output list
    add_basic_edges(sentence)
    
    return sentence


def serialize_spacy_doc(orig, converted_):
    # remove redundant dummy-root-node
    converted = {iid: tok for iid, tok in converted_.items() if iid != 0}
    
    # get attributes of original doc
    attrs_ = list(attrs.NAMES)
    attrs_.remove('SENT_START')  # this clashes HEAD (see spacy documentation)
    attrs_.remove('SPACY')  # we dont want to override the spaces we assign later on
    orig_attrs = orig.to_array(attrs_)
    
    # append copied attributes for new nodes
    new_nodes_attrs = [orig_attrs[round(iid)] for iid, tok in converted.items() if int(iid) != iid]
    if new_nodes_attrs:
        new_attrs = np.append(orig_attrs, new_nodes_attrs, axis=0)
    else:
        new_attrs = orig_attrs
    
    # fix whitespaces in case of new nodes: take original spaces. change the last one if there are new nodes.
    #   add spaces for each new nodes, except for last
    spaces = [t.whitespace_ if not ((i + 1 == len(orig)) and (len(new_nodes_attrs) > 0)) else ' ' for i, t in enumerate(orig)] + \
             [' ' if i + 1 < len(converted.keys()) else '' for i, iid in enumerate(converted.keys()) if int(iid) != iid]
    
    # form new doc including new nodes and set attributes
    new_doc = Doc(orig.vocab, words=[t.get_conllu_field("form") for iid, t in converted.items()], spaces=spaces)
    new_doc.from_array(attrs_, new_attrs)
    
    # store spacy ids for head indices extraction later on
    spacy_ids = {iid: spacy_i for spacy_i, iid in enumerate(converted.keys())}
    
    # set new info for all tokens per their head lists
    for spacy_tok, brat_tok in zip(new_doc, converted.values()):
        for head, rel in brat_tok.get_new_relations():
            # extract spacy correspondent  head id
            head_tok = new_doc[spacy_ids[head.get_conllu_field("id")] if head.get_conllu_field("id") != 0 else spacy_tok.i]
            # parse stringish label
            is_state_head_node = ((head_tok.text == "STATE") and (head.get_conllu_field("id") != int(head.get_conllu_field("id")))) or \
                                 (brat_tok.get_conllu_field("id") != int(brat_tok.get_conllu_field("id")))
            new_rel, src, unc, alt = parse_bart_label(rel, is_state_head_node=is_state_head_node)
            # add info to token
            spacy_tok._.parent_list.append({'head': head_tok, 'rel': new_rel, 'src': src, 'alt': alt, 'unc': unc})
    
    return new_doc
