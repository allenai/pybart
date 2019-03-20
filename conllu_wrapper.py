from collections import namedtuple

# format of CoNLL-u as described here: https://universaldependencies.org/format.html
ConlluInfo = namedtuple("ConlluInfo", "id, form, lemma, upos, xpos, feats, head, deprel, deps, misc, ner")


def replace_conllu_info(
        node, new_id=None, form=None, lemma=None, upos=None, xpos=None, feats=None, head=None, deprel=None, deps=None, misc=None, ner=None):
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
        node["conllu_info"].misc if not misc else misc,
        node["conllu_info"].ner if not ner else ner)


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
    found_ner = False
    sentences = []
    for sent in text.strip().split('\n\n'):
        lines = sent.strip().split('\n')
        if lines:
            while lines[0].startswith('#'):
                lines.pop(0)
            sentence = dict()
            for line in lines:
                parts = line.split()
                ner = None
                if len(parts) == 11:
                    ner = parts[10]
                    found_ner = True
                elif len(parts) != 10:
                    raise Exception("incorrect amount of data for token")
                new_id, form, lemma, upos, xpos, feats, head, deprel, deps, misc = parts[:10]
                
                if '-' in new_id or '.' in new_id:
                    # TODO - add a print and a raise since they shouldn't appear here
                    continue
                try:
                    if deps != '_':
                        raise Exception
                    xpos = upos if xpos == '_' else xpos  # TODO - is needed?
                    sentence[int(new_id)] = {
                        'conllu_info': ConlluInfo(int(new_id), form, lemma, upos, xpos, feats, int(head), deprel, deps, misc, ner),
                        'head_pointer': None,
                        'children_list': [],
                        'new_deps': [False, {int(head): deprel}]}
                except:
                    print(line)
                    raise
            sentences.append(sentence)
    post_process(sentences)
    return sentences, found_ner


def serialize_conllu(converted):
    # TODO - recover comments from original file?
    text = ''
    
    for sentence in converted:
        new_deps_changed = True in [val['new_deps'][0] for val in sentence.values()]
        for (cur_id, token) in sentence.items():
            for field, field_name in zip(token['conllu_info'], token['conllu_info']._fields):
                if field_name == 'deps' and new_deps_changed:
                        text += "|".join(sorted([(str(a) + ":" + b) for (a, b) in token['new_deps'][1].items()])) + '\t' # TODO - validate the result is ordered
                elif field_name == 'misc':
                    text += str(field) + ('\n' if token['conllu_info'].ner is None else '\t')
                elif field_name == 'ner':
                    if token['conllu_info'].ner is not None:
                        text += str(field) + '\n'
                else:
                    text += str(field) + '\t'
        text += '\n'
    
    return text
