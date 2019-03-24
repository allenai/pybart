import configuration as conf
from token import Token


def exchange_pointers(sentence):
    """Purpose: adds each node to its corresponding parents "children_list".
    
    Args:
        (dict) The parsed sentence.
    """
    for (cur_id, token) in sentence.items():
        currents_head = token.get_conllu_info()['head']
        
        # only if node isn't root
        if token.is_root():
            # add the head as the Token itself
            token.add_parent(sentence[currents_head])
            
            # add to target head, the current node as child
            sentence[currents_head].add_child(token)


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
    for sent in text.strip().split('\n\n'):
        lines = sent.strip().split('\n')
        if not lines:
            continue
        
        comments = []
        sentence = dict()
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
            sentence[int(new_id)] = Token(
                    int(new_id), form, lemma, upos, xpos, feats, int(head), deprel, deps, misc)
        
        # after parsing entire sentence, exchange information between tokens,
        # and add sentence to output list
        exchange_pointers(sentence)
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
    text = ''
    
    for (sentence, comments) in zip(converted, all_comments):
        # recover comments from original file
        if conf.preserve_comments:
            for comment in comments:
                text += comment + '\n'
        
        for (cur_id, token) in sentence.items():
            # add every field of the given token
            for field_name, field in token.get_conllu_info():
                # for 'deps' field, we need to sort the new relations and then add them with '|' separation,
                # as required by the format.
                # check if new_deps has changed for at least one token, otherwise,
                # check if we want to add it to the output or preserve SC behavior.
                if field_name == 'deps' and (conf.output_unchanged_deps or token.is_new_deps_changed()):
                        sorted_new_deps = sorted([(str(a) + ":" + b) for (a, b) in token.get_new_deps_pairs()])
                        text += "|".join(sorted_new_deps) + '\t'
                # misc is the last one so he needs a spacial case for the new line character.
                elif field_name == 'misc':
                    text += str(field) + '\n'
                # simply add the rest of the fields with a tab separator.
                else:
                    text += str(field) + '\t'
        
        # add an empty line after a sequence of tokens, that is after finishing a complete sentence.
        text += '\n'
    
    return text
