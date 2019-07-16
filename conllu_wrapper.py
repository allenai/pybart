import uuid
import graph_token
import json

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


# fw.conllu_to_odin(converter.convert(fw.parse_conllu(fw.odin_to_conllu(json_buf)[0])))
# or better off: fw.conllu_to_odin(converter.convert(fw.parse_odin(json_buf))))
def parse_odin(odin_buf):
    odin_dict = json.load(odin_buf)
    sentences = []
    for sent in odin_dict['sentences']:
        sentence = {0: graph_token.Token(0, None, None, None, None, None, None, None, None, None)}
        for i, (word, tag, lemma) in enumerate(zip(sent['words'], sent['tags'], sent['lemma'])):
            sentence[i + 1] = graph_token.Token(i + 1, word, lemma, "_", tag, "_", "_", "_", "_", "_")
        for edge in sent['graphs']['universal-basic']:
            sentence[edge['dest']].set_conllu_field('head', edge['source'])
            sentence[edge['dest']].set_conllu_field('deprel', edge['relation'])
        for root in sent['graphs']['universal-basic']:
            sentence[root].set_conllu_field('head', 0)
            sentence[root].set_conllu_field('deprel', "root")
        add_basic_edges(sentence)
        sentences.append(sentence)
    
    return sentences


def conllu_to_odin_single_sentence(conllu_sentence, is_basic, odin_sentence=None):
    if is_basic and not odin_sentence:
        graph = "universal-basic"
    else:
        graph = "universal-aryeh"
    
    change_only_graph = True
    if not odin_sentence:
        odin_sentence = {"words": [], "tags": [], "graphs": {graph: {"edges": [], "roots": []}}}
        change_only_graph = False
        
    for iid, token in conllu_sentence.items():
        if iid == 0:
            continue
        if not change_only_graph:
            odin_sentence["words"].append(token.get_conllu_field("form"))
            odin_sentence["tags"].append(token.get_conllu_field("xpos"))
        
        if token.is_root_node():
            odin_sentence["graphs"][graph]["roots"].append(iid - 1)
            continue
        
        if is_basic:
            if token.get_conllu_field("deprel") == "root":
                continue
            odin_sentence["graphs"][graph]["edges"].append(
                {"source": token.get_conllu_field("head") - 1, "destination": iid - 1,
                 "relation": token.get_conllu_field("deprel")})
        else:
            for head, rel in token.get_new_relations():
                if rel == "root":
                    continue
                odin_sentence["graphs"][graph]["edges"].append(
                    {"source": head.get_conllu_field("id") - 1, "destination": iid - 1, "relation": rel})
    return odin_sentence


def conllu_to_odin(conllu_sentences, is_basic=False, odin_to_enhance=None):
    odin_sentences = []
    
    for i, conllu_sentence in enumerate(conllu_sentences):
        odin_sentences.append(conllu_to_odin_single_sentence(conllu_sentence, is_basic, odin_to_enhance['sentences'][i] if odin_to_enhance else None))
    
    if odin_to_enhance:
        odin_to_enhance['sentences'] = odin_sentences
        odin = odin_to_enhance
    else:
        odin = {"documents": {"": {
            "id": str(uuid.uuid4()),
            "text": " ".join([token.get_conllu_field("form") for conllu_sentence in conllu_sentences for token in conllu_sentence.values() if token.get_conllu_field("id") != 0]),
            "sentences": odin_sentences
        }}, "mentions": []}
        print(odin['documents']['']['text'])
    return odin
