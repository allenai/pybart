import struct
from spacy.tokens import Doc, Token as SpacyToken
from spacy import attrs
import numpy as np

from .graph_token import Token, add_basic_edges

NUM_OF_BITS = struct.calcsize("P") * 8


# this is here because it needs to happen only once (per import)
SpacyToken.set_extension("parent_list", default=[])


def parse_spacy_sent(sent):
    sentence = []

    offset = min(tok.i for tok in sent)
    
    for i, tok in enumerate(sent):
        # add current token to current sentence
        sentence.append(Token(
            tok.i + 1 - offset, tok.text, tok.lemma_, tok.pos_, tok.tag_, "_", (tok.head.i + 1 - offset) if tok.head.i != tok.i else 0,
            tok.dep_.lower(), "_", "_"))
    
    # add root
    sentence.append(Token(0, None, None, None, None, None, None, None, None, None))
    
    # after parsing entire sentence, add basic deprel edges,
    # and add sentence to output list
    add_basic_edges(sentence)
    
    return sentence


def parse_bart_label(rel, is_state_head_node):
    if rel.src is not None:
        src = (rel.src,) + tuple(filter(None, [rel.src_type, rel.phrase]))
    else:
        src = "UD" if not is_state_head_node else "BART"
    
    return rel.with_no_bart(), src, bool(rel.uncertain), rel.alt


def serialize_spacy_doc(orig_doc, converted_sentences):
    words = []
    spaces = []
    total_attrs = []
    attrs_ = list(attrs.NAMES)
    attrs_.remove('SENT_START')  # this clashes HEAD (see spacy documentation)
    attrs_.remove('SPACY')  # we dont want to override the spaces we assign later on
    
    for orig_span, converted_sentence in zip(orig_doc.sents, converted_sentences):
        # remove redundant dummy-root-node
        converted = {iid: tok for iid, tok in converted_sentence.items() if iid != 0}
        orig = orig_span.as_doc()
        
        # get attributes of original doc
        orig_attrs = orig.to_array(attrs_)
        
        # append copied attributes for new nodes
        new_nodes_attrs = []
        for iid, tok in converted.items():
            if int(iid) != iid:
                new_node_attrs = list(orig_attrs[int(iid) - 1])
                
                # here we fix the relative head he is pointing to,
                # in case it is a negative number we need to cast it to its unsigned synonym
                relative = int(iid) - (len(orig_attrs) + len(new_nodes_attrs) + 1)
                new_node_attrs[attrs_.index('HEAD')] = relative + (2**NUM_OF_BITS if relative < 0 else 0)
                
                new_nodes_attrs.append(new_node_attrs)
        if new_nodes_attrs:
            new_attrs = np.append(orig_attrs, new_nodes_attrs, axis=0)
        else:
            new_attrs = orig_attrs
        total_attrs = np.append(total_attrs, new_attrs, axis=0) if len(total_attrs) > 0 else new_attrs
        
        # fix whitespaces in case of new nodes: take original spaces. change the last one if there are new nodes.
        #   add spaces for each new nodes, except for last
        spaces += [t.whitespace_ if not ((i + 1 == len(orig)) and (len(new_nodes_attrs) > 0)) else ' ' for i, t in enumerate(orig)] + \
                  [' ' if i + 1 < len(converted.keys()) else '' for i, iid in enumerate(converted.keys()) if int(iid) != iid]
        spaces[-1] = ' '
        words += [t.get_conllu_field("form") for iid, t in converted.items()]
    
    # form new doc including new nodes and set attributes
    spaces[-1] = ''
    new_doc = Doc(orig_doc.vocab, words=words, spaces=spaces)
    new_doc.from_array(attrs_, total_attrs)
    
    j = 0
    for converted_sentence in converted_sentences:
        converted = {iid: tok for iid, tok in converted_sentence.items() if iid != 0}

        # store spacy ids for head indices extraction later on
        spacy_ids = {iid: (spacy_i + j) for spacy_i, iid in enumerate(converted.keys())}
        
        # set new info for all tokens per their head lists
        for i, bart_tok in enumerate(converted.values()):
            spacy_tok = new_doc[i + j]
            for head, rel in bart_tok.get_new_relations():
                # extract spacy correspondent head id
                head_tok = new_doc[spacy_ids[head.get_conllu_field("id")] if head.get_conllu_field("id") != 0 else spacy_tok.i]
                # parse stringish label
                is_state_head_node = ((head_tok.text == "STATE") and (head.get_conllu_field("id") != int(head.get_conllu_field("id")))) or \
                                     (bart_tok.get_conllu_field("id") != int(bart_tok.get_conllu_field("id")))
                new_rel, src, unc, alt = parse_bart_label(rel, is_state_head_node=is_state_head_node)
                # add info to token
                spacy_tok._.parent_list.append({'head': head_tok, 'rel': new_rel, 'src': src, 'alt': alt, 'unc': unc})
            
            # fix sentence boundaries, need to turn off is_parsed bool as it prevents setting the boundaries
            new_doc.is_parsed = False
            spacy_tok.is_sent_start = False if i != 0 else True
            new_doc.is_parsed = True
        
        j += len(converted)
    
    return new_doc
