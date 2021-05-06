import struct
from typing import Any, Dict
import os
import sys

from spacy.tokens import Doc, Token as SpacyToken
from spacy.tokens.graph import Graph

from .graph_token import Token, add_basic_edges, TokenId

JsonObject = Dict[str, Any]


# this is here because it needs to happen only once (per import)
Doc.set_extension("parent_graphs_per_sent", default=[])
Doc.set_extension("added_nodes", default=[])


def get_pybart(doc):
    ret = []
    for i, (graph, sent) in enumerate(zip(doc._.parent_graphs_per_sent, doc.sents)):
        offset = sent[0].i
        ret.append([])
        for edge in graph.edges:
            ret[i].append({
                "head": doc[edge.head.i + offset] if edge.head.i < len(sent) else doc._.added_nodes[i][edge.head.i],
                "tail": doc[edge.tail.i + offset] if edge.tail.i < len(sent) else doc._.added_nodes[i][edge.tail.i],
                "label": edge.label_
            })
    return ret


Doc.set_extension("get_pybart", method=get_pybart)


def enhance_spike_doc(doc: Doc, spike_doc: JsonObject) -> JsonObject:
    converted_graphs = doc._.parent_graphs_per_sent
    for idx, sent in enumerate(spike_doc["sentences"]):
        sent["graphs"]["universal-enhanced"] = {"edges": [], "roots": []}
        for edge in converted_graphs[idx].edges:
            if edge.label_.lower().startswith("root"):
                sent["graphs"]["universal-enhanced"]["roots"].append(edge.tail.i)  # assume we have only one token per graph node
            else:
                sent["graphs"]["universal-enhanced"]["edges"].append(
                    {"source": edge.head.i, "destination": edge.tail.i, "relation": edge.label_})
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
    for sent_idx, (orig_span, converted_sentence) in enumerate(zip(orig_doc.sents, converted_sentences)):
        added_counter = 0
        node_indices_map = dict()
        nodes = []
        edges = []
        labels = []
        orig_doc._.added_nodes.append(dict())
        converted_sentence = [tok for tok in converted_sentence if tok.get_conllu_field("id") != '0']
        for idx, tok in enumerate(converted_sentence):
            new_id = tok.get_conllu_field("id")
            node_indices_map[new_id.token_str] = idx
            _ = nodes.append((idx,))
            if new_id.minor != 0:
                orig_doc._.added_nodes[sent_idx][idx] = tok.get_conllu_field("form") + (f"_{added_counter}" if tok.get_conllu_field("form") == "STATE" else f"[COPY_NODE_{added_counter}]")
                added_counter += 1
        for tok in converted_sentence:
            new_id = tok.get_conllu_field("id").token_str
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
