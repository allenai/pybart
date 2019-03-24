from collections import namedtuple

# format of CoNLL-u as described here: https://universaldependencies.org/format.html
ConlluInfo = namedtuple("ConlluInfo", "id, form, lemma, upos, xpos, feats, head, deprel, deps, misc")


def replace_conllu_info(
        node, new_id=None, form=None, lemma=None, upos=None, xpos=None,
        feats=None, head=None, deprel=None,deps=None, misc=None):
    """Purpose: Creates a new ConlluInfo tuple.
    
    Args:
        ConlluInfo fields
    
    Comments:
        As we can't change the fields of a tuple,
        we must restore all the original fields except those we wish to change.
        This might seem like an overhead but the named tuple is much more readable while using it.
    """

    node["conllu_info"] = ConlluInfo(
        node["conllu_info"].id if not new_id else new_id,
        node["conllu_info"].form if not form else form,
        node["conllu_info"].lemma if not lemma else lemma,
        node["conllu_info"].upos if not upos else upos,
        node["conllu_info"].xpos if not xpos else xpos,
        node["conllu_info"].feats if not feats else feats,
        node["conllu_info"].head if not head else head,
        node["conllu_info"].deprel if not deprel else deprel,
        node["conllu_info"].deps if not deps else deps,
        node["conllu_info"].misc if not misc else misc)


def exchange_pointers(sentence):
    """Purpose: adds each node to its corresponding parents "children_list".
    
    Args:
        (dict) The parsed sentence.
    """
    for (cur_id, token) in sentence.items():
        currents_head = sentence[cur_id]['conllu_info'].head
        # only if node isn't root
        if currents_head != 0:
            # add the head as the Token itself (TODO - either use, or remove)
            sentence[cur_id]['head_pointer'] = sentence[currents_head]
            
            # add to target head, the current node as child
            sentence[currents_head]['children_list'].append(sentence[cur_id])


def parse_conllu(text):
    """Purpose: parses the given CoNLL-U formatted text.
    
    Args:
        (str) The text.
    
    returns:
        (list(dict)) returns a list of sentence dicts.
        a sentence dict is a mapping from id to token/word.
        a token is a dict of ConlluInfo, list of children nodes, pointer to head, and dict of new relations.
        TODO - add a Token class for simplicity and modularity.
        
     Raises:
         ValueError: text must be a basic CoNLL-U, received an enhanced one.
         ValueError: text must be a basic CoNLL-U format, received a CoNLL-X format.
]    """
    sentences = []
    for sent in text.strip().split('\n\n'):
        lines = sent.strip().split('\n')
        if lines:
            # ignore comments
            while lines[0].startswith('#'):
                lines.pop(0)
            sentence = dict()
            for line in lines:
                # split line by any whitespace, and store the first 10 columns.
                parts = line.split()
                new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc = parts[:10]
                
                # validate input
                if '-' in new_id:
                    raise ValueError("text must be a basic CoNLL-U format, received a CoNLL-X format.")
                if deps != '_' or '.' in new_id:
                    raise ValueError("text must be a basic CoNLL-U, received an enhanced one.")
                
                try:
                    # fix xpos if empty to a copy of upos (TODO - is this really needed?)
                    xpos = upos if xpos == '_' else xpos
                    
                    # add current token to current sentence
                    sentence[int(new_id)] = {
                        'conllu_info': ConlluInfo(int(new_id), form, lemma, upos, xpos, feats, int(head), deprel, deps, misc),
                        'head_pointer': None,
                        'children_list': [],
                        'new_deps': [False, {int(head): deprel}]}
                finally:
                    print(line)
            
            # after parsing entire sentence, exchange information between tokens,
            # and add sentence to output list
            exchange_pointers(sentence)
            sentences.append(sentence)
    
    return sentences


def serialize_conllu(converted):
    """Purpose: create a CoNLL-U formatted text from a sentence list.
    
    Args:
        (list(dict(Token))) The sentence list.
    
    returns:
        (str) the text corresponding to the sentence list in the CoNLL-U format.
     """
    # TODO - recover comments from original file?
    text = ''
    
    for sentence in converted:
        # check if new_deps has changed for at least one token, otherwise we won't add it to the output.
        # this is mimicking the SC behavior. (TODO - do we want to presarve this behavior?)
        new_deps_changed = True in [val['new_deps'][0] for val in sentence.values()]
        
        for (cur_id, token) in sentence.items():
            # add every field of the given token
            for field, field_name in zip(token['conllu_info'], token['conllu_info']._fields):
                # for 'deps' field, we need to sort the new relations and then add them with '|' separation,
                # as required by the format.
                if field_name == 'deps' and new_deps_changed:
                        text += "|".join(sorted([(str(a) + ":" + b) for (a, b) in token['new_deps'][1].items()])) + '\t' # TODO - validate the result is ordered
                # misc is the last one so he needs a spacial case for the new line character.
                elif field_name == 'misc':
                    text += str(field) + '\n'
                # simply add the rest of the fields with a tab separator.
                else:
                    text += str(field) + '\t'
        
        # add an empty line after a sequence of tokens, that is after finishing a complete sentence.
        text += '\n'
    
    return text
