from collections import namedtuple

# format of CoNLL-u as described here: https://universaldependencies.org/format.html
ConlluInfo = namedtuple("ConlluInfo", "id, form, lemma, upos, xpos, feats, head, deprel, deps, misc")


def post_process(parsed):
    for i, sentence in enumerate(parsed):
        for (cur_id, token) in sentence.items():
            # only if node isn't root
            currents_head = sentence[cur_id]['conllu_info'].head
            if currents_head != 0:
                # add the head as the Token itself
                sentence[cur_id]['head_pointer'] = sentence[currents_head]
                
                # add to target head, the current node as child
                sentence[currents_head]['children_list'].append(sentence[cur_id])


# adapted from https://github.com/explosion/spaCy/blob/master/spacy/cli/converters/conllu2json.py
# which was actually conllx :O
def parse_conllu(text):
    sentences = []
    for sent in text.strip().split('\n\n'):
        lines = sent.strip().split('\n')
        if lines:
            while lines[0].startswith('#'):
                lines.pop(0)
            sentence = dict()
            for line in lines:
                parts = line.split('\t')
                id, form, lemma, upos, xpos, feats, head, deprel, deps, misc = parts
                if '-' in id or '.' in id:
                    # TODO - add a print and a raise since they shouldn't appear here
                    continue
                try:
                    if deps != '_':
                        raise Exception
                    xpos = upos if xpos == '_' else xpos  # TODO - is needed?
                    sentence[int(id)] = {'conllu_info': ConlluInfo(int(id), form, lemma, upos, xpos, feats, int(head), deprel, deps, misc),
                                         'head_pointer': None,
                                         'children_list': [],
                                         'new_deps': {int(head): deprel}}
                except:
                    print(line)
                    raise
            sentences.append(sentence)
    post_process(sentences)
    return sentences


def serialize_conllu(converted):
    # TODO - recover comments from original file?
    text = ''
    
    for sentence in converted:
        for (cur_id, token) in sentence.items():
            for field, field_name in zip(token['conllu_info'], token['conllu_info']._fields):
                if field_name == 'deps':
                    text += "|".join(sorted([(str(a) + ":" + b) for (a, b) in token['new_deps'].items()])) + '\t' # TODO - validate the result is ordered
                elif field_name == 'misc':
                    text += str(field) + '\n'
                else:
                    text += str(field) + '\t'
        text += '\n'
    
    return text


def test():
    parsed = parse_conllu(open("test2.conllu", "r").read())
    print(serialize_conllu(parsed))
    
