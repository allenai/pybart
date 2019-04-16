import configuration as conf
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


def serialize_conllu(converted, all_comments):
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
        if conf.preserve_comments:
            comments = ["\n".join(per_sent_comments)]
        
        # TODO - fix case of more than 9 copy nodes - needs special ordering e.g 1.1 ... 1.9 1.10 and not 1.1 1.10 ... 1.9
        text.append(comments + [token.get_conllu_string() for (cur_id, token) in sorted(sentence.items()) if cur_id != 0])
    
    return "\n".join(["\n".join(sent) + "\n" for sent in text])
