import struct
from typing import Any, Dict
import os
import sys

from spacy.tokens import Doc, Token as SpacyToken
from spacy.tokens.graph import Graph

from .graph_token import Token, add_basic_edges, TokenId

JsonObject = Dict[str, Any]
NUM_OF_BITS = struct.calcsize("P") * 8


# this is here because it needs to happen only once (per import)
Doc.set_extension("parent_graphs_per_sent", default=[])


def enhance_spike_doc(doc: Doc, spike_doc: JsonObject) -> JsonObject:
    converted_graphs = doc._.parent_graphs_per_sent
    for idx, sent in enumerate(spike_doc["sentences"]):
        offset = min(token for node in converted_graphs[idx].nodes for token in node)
        sent["graphs"]["universal-enhanced"] = {"edges": [], "roots": []}
        for edge in converted_graphs[idx].edges:
            if edge.label_.lower().startswith("root"):
                sent["graphs"]["universal-enhanced"]["roots"].append(edge.tail.tokens[0].i - offset)  # assume we have only one token per graph node
            else:
                sent["graphs"]["universal-enhanced"]["edges"].append(
                    {"source": edge.head.tokens[0].i - offset, "destination": edge.tail.tokens[0].i - offset, "relation": edge.label_})
        # sort the roots and edges for consistency purposes
        sent["graphs"]["universal-enhanced"]["roots"] = sorted(sent["graphs"]["universal-enhanced"]["roots"])
        sent["graphs"]["universal-enhanced"]["edges"] = sorted(sent["graphs"]["universal-enhanced"]["edges"],
                                                               key=lambda x: (x['source'], x['destination'], x['relation']))
    return spike_doc


Doc.set_extension("enhance_spike_doc", method=enhance_spike_doc)


def parse_spacy_sent(sent):
    sentence = []

    offset = min(tok.i for tok in sent)
    
    for i, tok in enumerate(sent):
        # add current token to current sentence
        sentence.append(Token(
            TokenId(tok.i + 1 - offset), tok.text, tok.lemma_, tok.pos_, tok.tag_, "_",
            TokenId((tok.head.i + 1 - offset) if tok.head.i != tok.i else 0), tok.dep_.lower(), "_", "_"))
    
    # add root
    sentence.append(Token(TokenId(0), None, None, None, None, None, None, None, None, None))
    
    # after parsing entire sentence, add basic deprel edges,
    # and add sentence to output list
    add_basic_edges(sentence)
    
    return sentence


def enhance_to_spacy_doc(orig_doc, converted_sentences, remove_enhanced_extra_info, remove_bart_extra_info):
    offset = 0
    for orig_span, converted_sentence in zip(orig_doc.sents, converted_sentences):
        node_indices_map = dict()
        nodes = []
        edges = []
        labels = []
        for idx, tok in enumerate(converted_sentence):
            new_id = tok.get_conllu_field("id")
            if new_id == '0':
                continue
            node_indices_map[new_id.token_str] = idx
            _ = nodes.append((new_id.major - 1 + offset,) if new_id.minor == 0 else ())
        for idx, tok in enumerate(converted_sentence):
            new_id = tok.get_conllu_field("id").token_str
            if new_id == '0':
                continue
            for head, rels in tok.get_new_relations():
                for rel in rels:
                    head_id = head.get_conllu_field("id").token_str
                    edges.append((
                        node_indices_map[head_id if head_id != '0' else new_id],
                        node_indices_map[new_id]
                    ))
                    _ = orig_doc.vocab[rel.to_str(remove_enhanced_extra_info, remove_bart_extra_info)]  # this will push the label into the vocab if it's not there
                    labels.append(rel.to_str(remove_enhanced_extra_info, remove_bart_extra_info))

        # Disable printing possibility: so graph creation wont print many lines
        sys.stdout = open(os.devnull, 'w')
        orig_doc._.parent_graphs_per_sent.append(Graph(orig_doc, name="pybart", nodes=nodes, edges=edges, labels=labels))
        # Restore printing possibility
        sys.stdout = sys.__stdout__
        offset += len(orig_span)
