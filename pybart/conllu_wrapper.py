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


# fw.conllu_to_spike(converter.convert(fw.parse_conllu(fw.spike_to_conllu(json_buf)[0])))
# or better off: fw.conllu_to_spike(converter.convert(fw.parse_spike(json_buf))))
def parse_spike(spike_json):
    sentences = []
    for sent in spike_json['sentences']:
        sentence = list()
        for i, (word, tag, lemma) in enumerate(zip(sent['words'], sent['tags'], sent['lemmas'])):
            sentence.append(Token(TokenId(i + 1), word, lemma, "_", tag, "_", None, "_", "_", "_"))
        for edge in sent['graphs']['universal-basic']['edges']:
            sentence[edge['destination'] + 1].set_conllu_field('head', TokenId(edge['source'] + 1))
            sentence[edge['destination'] + 1].set_conllu_field('deprel', edge['relation'])
        for root in sent['graphs']['universal-basic']['roots']:
            sentence[root + 1].set_conllu_field('head', TokenId(0))
            sentence[root + 1].set_conllu_field('deprel', "root")
        sentence.append(Token(TokenId(0), None, None, None, None, None, None, None, None, None))

        add_basic_edges(sentence)
        sentences.append(sentence)
    
    return sentences


def _fix_sentence_keep_order(conllu_sentence):
    sorted_sent = sorted(conllu_sentence)
    addon = 0
    fixed = list()
    
    for token in sorted_sent:
        iid = token.get_conllu_field("id")
        if token.get_conllu_field("id").minor != 0:
            if "CopyOf" in token.get_conllu_field("misc"):
                token.set_conllu_field("form", token.get_conllu_field("form") + "[COPY_NODE]")
            addon += 1
        
        new_id = iid.major + addon
        token.set_conllu_field("id", TokenId(new_id))
        fixed.append(token)
    
    return fixed


def _fix_sentence_push_to_end(conllu_sentence):
    fixed = list()

    for i, token in enumerate(conllu_sentence):
        iid = token.get_conllu_field("id")
        if iid.major == 0:
            continue
        if iid.get_conllue_field("id").major != 0:
            token.set_conllu_field("id", TokenId(i + 1))
        
        fixed.append(token)
    
    return fixed


def fix_sentence(conllu_sentence, push_new_to_end=True):
    if push_new_to_end:
        return _fix_sentence_push_to_end(conllu_sentence)
    else:
        return _fix_sentence_keep_order(conllu_sentence)


def fix_graph(conllu_sentence, spike_sentence, is_basic, remove_enhanced_extra_info, remove_bart_extra_info):
    if is_basic:
        spike_sentence["graphs"] = {"universal-basic": {"edges": [], "roots": []}}
    else:
        if 'graphs' in spike_sentence:
            spike_sentence["graphs"]["universal-enhanced"] = {"edges": [], "roots": []}
        else:
            spike_sentence["graphs"] = {"universal-enhanced": {"edges": [], "roots": []}}

    for iid, token in enumerate(conllu_sentence):
        if token.get_conllu_field("id").major == 0:
            continue
        
        if is_basic:
            if token.get_conllu_field("deprel").lower().startswith("root"):
                spike_sentence["graphs"]["universal-basic"]["roots"].append(iid)
            else:
                spike_sentence["graphs"]["universal-basic"]["edges"].append(
                    {"source": token.get_conllu_field("head").major - 1, "destination": iid,
                     "relation": token.get_conllu_field("deprel")})
        else:
            for head, rels in token.get_new_relations():
                for rel in rels:
                    if rel.to_str(remove_enhanced_extra_info, remove_bart_extra_info).lower().startswith("root"):
                        spike_sentence["graphs"]["universal-enhanced"]["roots"].append(iid)
                    else:
                        spike_sentence["graphs"]["universal-enhanced"]["edges"].append(
                            {"source": head.get_conllu_field("id").major - 1, "destination": iid, "relation": rel.to_str(remove_enhanced_extra_info, remove_bart_extra_info)})
    
    return spike_sentence


def append_spike(spike_sent, fixed_sentence, text):
    cur_sent_text = text
    cur_offset = 0
    
    for node in fixed_sentence[len(spike_sent['words']):]:
        if node.get_conllu_field('id').major == 0:
            continue
        
        if 'words' in spike_sent:
            spike_sent['words'].append(node.get_conllu_field('form'))
        if 'raw' in spike_sent:
            spike_sent['raw'].append(node.get_conllu_field('form'))
        if 'tags' in spike_sent:
            spike_sent['tags'].append(node.get_conllu_field('xpos'))
        if 'entities' in spike_sent:
            spike_sent['entities'].append('O')
        if ('startOffsets' in spike_sent) and ('endOffsets' in spike_sent):
            spike_sent['startOffsets'].append(spike_sent['endOffsets'][-1] + 1)
            spike_sent['endOffsets'].append(spike_sent['startOffsets'][-1] + len(node.get_conllu_field('form')))
        if 'lemmas' in spike_sent:
            spike_sent['lemmas'].append(node.get_conllu_field('lemma'))
        if 'chunks' in spike_sent:
            spike_sent['chunks'].append('O')
        
        cur_sent_text += " " + node.get_conllu_field('form')
        cur_offset += len(" " + node.get_conllu_field('form'))
    
    return spike_sent, cur_sent_text, cur_offset


def fix_offsets(spike_sent, all_offset):
    if ('startOffsets' in spike_sent) and ('endOffsets' in spike_sent):
        spike_sent['startOffsets'] = [(current + all_offset) for current in spike_sent['startOffsets']]
        spike_sent['endOffsets'] = [(current + all_offset) for current in spike_sent['endOffsets']]
    

def conllu_to_spike(conllu_sentences, spike_to_enhance=None, is_basic=False, push_new_to_end=True, remove_enhanced_extra_info=False, remove_bart_extra_info=True):
    spike_sentences = []
    fixed_sentences = []
    texts = []
    summed_offset = 0
    
    for i, conllu_sentence in enumerate(conllu_sentences):
        fixed_sentence = conllu_sentence
        
        if spike_to_enhance:
            text = spike_to_enhance['text'][spike_to_enhance['sentences'][i]['startOffsets'][0]: spike_to_enhance['sentences'][i]['endOffsets'][-1]]
            
            # fixing offsets may be to all sentences, as previous sentences may have become longer, changing all following offsets
            fix_offsets(spike_to_enhance['sentences'][i], summed_offset)
        
        # when added nodes appear fix sent
        if any([tok.get_conllu_field("id").minor != 0 for tok in conllu_sentence]):
            fixed_sentence = fix_sentence(fixed_sentence, push_new_to_end)
            if spike_to_enhance:
                spike_to_enhance['sentences'][i], text, cur_offset = append_spike(spike_to_enhance['sentences'][i], fixed_sentence, text)
                summed_offset += cur_offset
        
        # store updated text for each sentence
        if spike_to_enhance:
            texts.append(text)
        
        # fix graph
        fixed_sentences.append(fixed_sentence)
        spike_sentences.append(fix_graph(
            fixed_sentence, spike_to_enhance['sentences'][i] if spike_to_enhance else
            {'words': [token.get_conllu_field("form") for token in fixed_sentence if token.get_conllu_field("id").major != 0],
             'tags': [token.get_conllu_field("xpos") for token in fixed_sentence if token.get_conllu_field("id").major != 0]},
            is_basic, remove_enhanced_extra_info, remove_bart_extra_info))
    
    if spike_to_enhance:
        spike_to_enhance['sentences'] = spike_sentences
        spike_to_enhance['text'] = "\n".join(texts)
        spike = spike_to_enhance
    else:
        spike = {"documents": {"": {
            "id": str(uuid.uuid4()),
            "text": " ".join([token.get_conllu_field("form") for conllu_sentence in fixed_sentences for token in
                              (sorted(conllu_sentence) if not push_new_to_end else conllu_sentence) if token.get_conllu_field("id").major != 0]),
            "sentences": spike_sentences
        }}, "mentions": []}
    
    return spike


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
