import uuid
import graph_token


def add_basic_edges(sentence):
    """Purpose: adds each basic deprel relation and the relevant father to its son.
    
    Args:
        (dict) The parsed sentence.
    """
    for (cur_id, token) in sentence.items():
        if cur_id == 0:
            continue
        
        # add the relation
        sentence[cur_id].add_edge(token.get_conllu_field('deprel'),
                                  sentence[token.get_conllu_field('head')])


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
        sentence = dict()
        
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
            sentence[int(new_id)] = graph_token.Token(
                    int(new_id), form, lemma, upos, xpos, feats, int(head), deprel, deps, misc)
        
        # add root
        sentence[0] = graph_token.Token(0, None, None, None, None, None, None, None, None, None)
        
        # after parsing entire sentence, add basic deprel edges,
        # and add sentence to output list
        add_basic_edges(sentence)
        sentences.append(sentence)
        all_comments.append(comments)
    
    return sentences, all_comments


def serialize_conllu(converted, all_comments, preserve_comments=False):
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
        
        # TODO - fix case of more than 9 copy nodes - needs special ordering e.g 1.1 ... 1.9 1.10 and not 1.1 1.10 ... 1.9
        text.append(comments + [token.get_conllu_string() for (cur_id, token) in sorted(sentence.items()) if cur_id != 0])
    
    return "\n".join(["\n".join(sent) + "\n" for sent in text])


def fix_ids(sentences, orig_sentence):
    new_sentences = []
    expected_i = 0
    found_at = 0
    orig_len = 0
    prev_token = None
    for i, sentence in enumerate(sentences):
        new_sentence = dict()
        prev_iid = 0
        for j, (iid, token) in enumerate(sentence.items()):
            if iid != 0:
                found_at = orig_sentence.find(token._conllu_info["form"], found_at + orig_len)
                orig_len = len(token._conllu_info["form"])
                if found_at != expected_i:
                    cur_start = expected_i
                    if prev_token:
                        if orig_sentence[expected_i:found_at].endswith(" "):
                            prev_end = found_at
                            cur_start = found_at
                        elif orig_sentence[expected_i:found_at].startswith(" "):
                            prev_end = expected_i
                        else:
                            prev_end = orig_sentence.find(" ", expected_i)
                            cur_start = orig_sentence.find(" ", expected_i) + 1
                        prev_token._conllu_info["form"] = prev_token._conllu_info["form"] + orig_sentence[expected_i:prev_end]
                    
                    end = ""
                    if ((i + 1) == len(sentences)) and ((j + 1) == (len(sentence.items()) - 1)):
                        end = orig_sentence[found_at + len(token._conllu_info["form"]):]
                    
                    token._conllu_info["form"] = orig_sentence[cur_start:found_at] + token._conllu_info["form"] + end
                expected_i = found_at + orig_len
                prev_token = token
            
            if iid != 0 and iid != prev_iid + 1:
                token._conllu_info["id"] = prev_iid + 1
                for iid2, token2 in sentence.items():
                    if token2.get_conllu_field("head") == iid:
                        token2._conllu_info["head"] = prev_iid + 1
                    for head, edges in token2._new_deps.items():
                        if head.get_conllu_field("id") == iid:
                            _ = token2._new_deps.pop(head)
                            token2._new_deps[sentence[prev_iid + 1]] = edges
            prev_iid = token.get_conllu_field("id")
            new_sentence[prev_iid] = token
        new_sentences.append(new_sentence)
    
    return new_sentences


def conllu_to_odin(conllu_sentences, orig_sentence, is_basic=False):
    odin_sentences = []
    all_words = []
    if is_basic:
        graph = "universal-basic"
    else:
        graph = "universal-plus"
    
    conllu_sentences = fix_ids(conllu_sentences, orig_sentence)
    
    for conllu_sentence in conllu_sentences:
        odin_sentence = {"words": [], "tags": [], "graphs": {graph: {"edges": [], "roots": []}}}
        for iid, token in conllu_sentence.items():
            if iid == 0:
                continue
            odin_sentence["words"].append(token.get_conllu_field("form"))
            all_words.append(token.get_conllu_field("form"))
            odin_sentence["tags"].append(token.get_conllu_field("xpos"))
            if token.is_root_node():
                odin_sentence["graphs"][graph]["roots"].append(iid - 1)
                continue
            if is_basic:
                if token.get_conllu_field("deprel") == "root":
                    continue
                odin_sentence["graphs"][graph]["edges"].append(
                    {"source": token.get_conllu_field("head") - 1, "destination": iid - 1, "relation": token.get_conllu_field("deprel")})
            else:
                for head, rel in token.get_new_relations():
                    if rel == "root":
                        continue
                    odin_sentence["graphs"][graph]["edges"].append(
                        {"source": head.get_conllu_field("id") - 1, "destination": iid - 1, "relation": rel})
        odin_sentences.append(odin_sentence)
    
    odin = {"documents": {"": {
        "id": str(uuid.uuid4()),
        "text": " ".join(all_words),
        "sentences": odin_sentences
    }}, "mentions": []}
    return odin
