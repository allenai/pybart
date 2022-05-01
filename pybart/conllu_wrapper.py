import uuid
from .graph_token import Token, add_basic_edges, TokenId


def parse_conllu(text):
    """Purpose: parses the given CoNLL-U formatted text.
    
    Args:
        (str) The text.
    
    returns:
        (list(dict(Token))) returns a list of sentence dicts.
            a sentence dict is a mapping from id to token/word.
        (list(list(str))) returns a list of comments list per sentence.
        
     Raises:
         ValueError: text must be a basic CoNLL-U, received an enhanced one.
         ValueError: text must be a basic CoNLL-U format, received a CoNLL-X format.
]    """
    sentences = []
    all_comments = []
    
    # for each sentence
    for sent in text.strip().split('\n\n'):
        lines = sent.strip().split('\n')
        if not lines:
            continue
        comments = []
        sentence = []
        
        # for each line (either comment or token)
        for line in lines:
            # store comments
            if line.startswith('#'):
                comments.append(line)
                continue
            
            # split line by any whitespace, and store the first 10 columns.
            parts = line.split()
            if len(parts) > 10:
                parts = line.split("\t")
                if len(parts) > 10:
                    raise ValueError("text must be a basic CoNLL-U format, received too many columns or separators.")
            
            new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc = parts[:10]
            
            # validate input
            if '-' in new_id:
                raise ValueError("text must be a basic CoNLL-U format, received a CoNLL-X format.")
            if deps != '_' or '.' in new_id:
                raise ValueError("text must be a basic CoNLL-U, received an enhanced one.")
            
            # fix xpos if empty to a copy of upos
            xpos = upos if xpos == '_' else xpos
            
            # add current token to current sentence
            sentence.append(Token(
                    TokenId(int(new_id)), form, lemma, upos, xpos, feats, TokenId(int(head)), deprel, deps, misc))
        
        # add root
        sentence.append(Token(TokenId(0), None, None, None, None, None, None, None, None, None))
        
        # after parsing entire sentence, add basic deprel edges,
        # and add sentence to output list
        add_basic_edges(sentence)
        sentences.append(sentence)
        all_comments.append(comments)
    
    return sentences, all_comments


def serialize_conllu(converted, all_comments, remove_enhanced_extra_info, remove_bart_extra_info, preserve_comments=False):
    """Purpose: create a CoNLL-U formatted text from a sentence list.
    
    Args:
        (list(dict(Token))) The sentence list.
    
    returns:
        (str) the text corresponding to the sentence list in the CoNLL-U format.
     """
    text = []
    comments = []
    for (sentence, per_sent_comments) in zip(converted, all_comments):
        # recover comments from original file
        if preserve_comments:
            comments = ["\n".join(per_sent_comments)]
        
        text.append(comments + [token.get_conllu_string(remove_enhanced_extra_info, remove_bart_extra_info) for token in sorted(sentence, key=lambda tok: tok.get_conllu_field("id")) if token.get_conllu_field("id").major != 0])
    
    return "\n".join(["\n".join(sent) + "\n" for sent in text])


def parse_spike_sentence(spike_sentence):
    sent = spike_sentence
    output = list()
    for i, (word, pos, lemma) in enumerate(zip(sent['words'], sent['pos'], sent['lemmas'])):
        output.append(Token(TokenId(i + 1), word, lemma, "_", pos, "_", None, "_", "_", "_"))
    for edge in sent['graphs']['universal-basic']['edges']:
        output[edge['child']].set_conllu_field('head', TokenId(edge['parent'] + 1))
        output[edge['child']].set_conllu_field('deprel', edge['label'])
    for root in sent['graphs']['universal-basic']['roots']:
        output[root].set_conllu_field('head', TokenId(0))
        output[root].set_conllu_field('deprel', "root")
    output.append(Token(TokenId(0), None, None, None, None, None, None, None, None, None))

    add_basic_edges(output)

    return output


def fix_graph(conllu_sentence, spike_sentence, remove_enhanced_extra_info, remove_bart_extra_info):
    if 'graphs' in spike_sentence:
        spike_sentence["graphs"]["universal-enhanced"] = {"edges": [], "roots": []}
    else:
        spike_sentence["graphs"] = {"universal-enhanced": {"edges": [], "roots": []}}

    for iid, token in enumerate(conllu_sentence):
        if token.get_conllu_field("id").major == 0:
            continue
        
        for head, rels in token.get_new_relations():
            for rel in rels:
                if rel.to_str(remove_enhanced_extra_info, remove_bart_extra_info).lower().startswith("root"):
                    spike_sentence["graphs"]["universal-enhanced"]["roots"].append(iid)
                else:
                    spike_sentence["graphs"]["universal-enhanced"]["edges"].append(
                        {"parent": head.get_conllu_field("id").major - 1, "child": iid, "label": rel.to_str(remove_enhanced_extra_info, remove_bart_extra_info)})
    
    return spike_sentence


def conllu_to_spike(conllu_sentences, spike_to_enhance, remove_enhanced_extra_info, remove_bart_extra_info):
    # ASSUMPTION - SPIKE doesnt allow node-adding conversions, so we dont need to fix text/offsets/etc
    spike_sentences = []

    for i, (conllu_sentence, spike_sentence) in enumerate(zip(conllu_sentences, spike_to_enhance['sentences'])):
        spike_sentences.append(
            fix_graph(conllu_sentence, spike_sentence, remove_enhanced_extra_info, remove_bart_extra_info)
        )
    
    spike_to_enhance['sentences'] = spike_sentences

    return spike_to_enhance


def parsed_tacred_json(data):
    sentences = []
    for d in data:
        sentence = dict()
        for i, (t, p, h, dep) in enumerate(
                zip(d["token"], d["stanford_pos"], d["stanford_head"], d["stanford_deprel"])):
            sentence[i + 1] = Token(i + 1, t, t, p, p, "_", int(h), dep, "_", "_")
        sentence[0] = Token(0, None, None, None, None, None, None, None, None, None)
        add_basic_edges(sentence)
        [child.remove_edge(rel, sentence[0]) for child, rels in sentence[0].get_children_with_rels() for rel in rels]
        _ = sentence.pop(0)
        sentences.append(sentence)
    
    return sentences
