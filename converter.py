###
# TODO:
#   1. what new_deps should be lowercased and lematization
#   2. where should we fix the deprel instead of deps
#   3. more docu!
#   4. recursive (such as conj)
###

import regex as re
import conllu_wrapper as cw

# configuration
enhance_only_nmods = False
tag_counter = 0


class Restriction(object):
        def __init__(self, dictionary):
            self._dictionary = {"name": None, "gov": None, "no-gov": None, "diff": None, "form": None, "nested": None}
            self._dictionary.update(dictionary)
        
        def __setitem__(self, key, item):
                if key not in self._dictionary:
                    raise KeyError("The key {} is not defined.".format(key))
                self._dictionary[key] = item
        
        def __getitem__(self, key):
            return self._dictionary[key]


# ----------------------------------------- matching functions ----------------------------------- #


def match(sent, cur_id, cur_name, restriction_lists, given_named_nodes=None):
    for restriction_list in restriction_lists:
        named_nodes = dict()
        if cur_name:
            named_nodes[cur_name] = sent[cur_id]
        
        one_restriction_violated = False
        for restriction in restriction_list:
            # first validate the restriction is not None,
            # this might happen if we build CONDITIONED restrictions.
            if not restriction:
                continue
            
            restriction_matched = False
            for child in sent[cur_id]['children_list']:
                inner_named_nodes = {}
                if restriction["gov"]:
                    if not re.match(restriction["gov"], child['conllu_info'].deprel):
                        continue
                
                if restriction["no-gov"]:
                    if re.match(restriction["no-gov"], child['conllu_info'].deprel):
                        break
                
                if restriction["nested"]:
                    inner_is_matched, inner_named_nodes = match(sent, child['conllu_info'].id, restriction["name"], restriction["nested"], named_nodes)
                    
                    if not inner_is_matched:
                        continue
                
                if restriction["diff"]:
                    found = False
                    for diff in restriction["diff"]:
                        named_child = None
                        if diff in named_nodes:
                            named_child = named_nodes[diff]
                        elif given_named_nodes and diff in given_named_nodes:
                            named_child = given_named_nodes[diff]
                        # In the beginning I thought this counts as a bug,
                        # But it can be used as a diff if we found a previous match and assigned it a name.
                        # else:
                        #     raise Exception("Restriction of unknown named node: " + restriction["diff"] + " ".join(named_nodes)
                        #                     + (" ".join(given_named_nodes) if given_named_nodes else ""))
                        
                        if named_child and not (named_child != child):
                            found = True
                    if found:
                        continue
                
                if restriction["form"]:
                    if not re.match(restriction["form"], child['conllu_info'].form):
                        continue
                
                if restriction["name"]:
                    named_nodes[restriction["name"]] = child
     
                named_nodes.update(inner_named_nodes)
                restriction_matched = True
                break
            
            if not restriction_matched:
                one_restriction_violated = True
                break
        
        if not one_restriction_violated:
            return True, named_nodes
        
    return False, None


# ----------------------------------------- replacing functions ---------------------------------- #


def add_edge(node, new_rel, new_spec=None, head=None, replace_deprel=False):
    global tag_counter
    rel_with_specs = new_rel + ((":" + new_spec) if new_spec else "")
    if replace_deprel:
        cw.replace_conllu_info(node, deprel=rel_with_specs)
        return
        
    head_id = node['conllu_info'].head if not head else head
    if head_id in node['new_deps'][1]:
        # TODO - this is not the ideal result, we want to have multigraph with same head here,
        # but this case should really never happen, and even stanford converter (SC) has here a BUG
        node['new_deps'][1][str(head_id) + "_" + str(tag_counter)] = rel_with_specs
        tag_counter += 1
    else:
        node['new_deps'][1][head_id] = rel_with_specs
    node['new_deps'][0] = True


def remove_edge(node, old_rel):
    node['new_deps'][1].pop(node['conllu_info'].head, old_rel)


def replace_edge(node, new_spec_list=None, new_rel=None, old_rel=None, replace_deprel=False):
    if not old_rel:
        old_rel = node['conllu_info'].deprel
    if not new_rel:
        new_rel = node['conllu_info'].deprel
    
    if not replace_deprel:
        remove_edge(node, old_rel)
    
    if new_spec_list:
        for new_spec in new_spec_list:
            add_edge(node, new_rel, new_spec=new_spec, replace_deprel=replace_deprel)
    else:
        add_edge(node, new_rel, replace_deprel=replace_deprel)


# ----------------------------------------- content functions ------------------------------------ #


def correct_subj_pass(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [[
            Restriction({"gov": 'auxpass'}),
            Restriction({"gov": "^(nsubj|csubj).*$", "name": "subj"})
        ]])
        if not is_matched:
            continue
        
        replace_edge(ret['subj'], new_rel=re.sub("subj", "subjpass", ret['subj']['conllu_info'].deprel), replace_deprel=True)


def passive_agent(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [[
            Restriction({"gov": 'nmod', "name": "mod", "nested": [[
                Restriction({"gov": 'case', "form": "^(?i:by)$"})
            ]]}),
            Restriction({"gov": "auxpass"})
        ]])
        if not is_matched:
            continue
        replace_edge(ret['mod'], new_spec_list=["agent"], replace_deprel=True)


def prep_patterns(sentence, used_cases, mw2=False, mw3=False, fix_nmods=True):
    if mw3 and mw2:
        raise Exception("mw2 and mw3 mustn't be both True")
    
    # to enhance nmods or acl/advcls markers
    if fix_nmods:
        first_gov = '^nmod$'
        second_gov = 'case'
    else:
        first_gov = '^(advcl|acl)$'
        second_gov = '^(mark|case)$'
    
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [[
            Restriction({"gov": first_gov, "name": "mod", "nested": [[
                Restriction({"gov": second_gov, "name": "c1", "form": "[^(by)]" if not (mw2 or mw3) else None, "nested": [[
                    Restriction({"gov": 'mwe', "name": "c2"}),
                    Restriction({"gov": 'mwe', "name": "c3", "diff": ["c2"]}) if mw3 else None
                ]] if mw2 or mw3 else None})
            ]]})
        ]])
        
        # We only want to match every case/marker once, so we test, and save them for further propagation
        # TODO - maybe a nicer and clearer way to do this?
        if not is_matched or            \
            ret['c1'] in used_cases or  \
            ('c2' in ret and ret['c2'] in used_cases) or  \
            ('c3' in ret and ret['c3'] in used_cases):
            continue
        used_cases += [ret['c1'], ret['c2'] if 'c2' in ret else None, ret['c3'] if 'c3' in ret else None]
        used_cases = [x for x in used_cases if x is not None]
        
        # we need to create a concat string for every marker neighbor chain
        # actually it should never happen that they are separate, but nonetheless we add relation if so,
        # as done in the stanford converter code
        # TODO - this complicated the function - maybe move to different function?
        strs_to_add = [ret['c1']['conllu_info'].form]
        if 'c2' in ret:
            if ret['c1']['conllu_info'].id == ret['c2']['conllu_info'].id - 1:
                strs_to_add[-1] += '_' + ret['c2']['conllu_info'].form
            else:
                strs_to_add.append(ret['c2']['conllu_info'].form)
            if 'c3' in ret:
                if ret['c2']['conllu_info'].id == ret['c3']['conllu_info'].id - 1:
                    strs_to_add[-1] += '_' + ret['c3']['conllu_info'].form
                else:
                    strs_to_add.append(ret['c3']['conllu_info'].form)
        
        replace_edge(
            ret['mod'],
            new_spec_list=strs_to_add,
            replace_deprel=False if len(strs_to_add) > 1 else True)


def conj_help_matcher(sentence, cur_id, ret_conj, matcher):
    is_matched = True
    i = 1
    given_named_nodes = {}
    while is_matched:
        is_matched, ret = match(sentence, cur_id, None, [[
            Restriction({"gov": matcher, "name": str(i) + matcher, "diff": given_named_nodes.keys()})
        ]], given_named_nodes=given_named_nodes)
        if is_matched:
            ret_conj.append((ret[str(i) + matcher]["conllu_info"].id, ret[str(i) + matcher]))
            given_named_nodes[str(i) + matcher] = ret[str(i) + matcher]
        i += 1
    
    return len(given_named_nodes) > 0


def conj_info(sentence):
    for (cur_id, token) in sentence.items():
        ret_conj = []
        if not conj_help_matcher(sentence, cur_id, ret_conj, "cc"):
            continue
        if not conj_help_matcher(sentence, cur_id, ret_conj, "conj"):
            continue
        
        cur_form = None
        for (id, conj) in sorted(ret_conj):
            if conj["conllu_info"].deprel == "cc":
                cur_form = conj["conllu_info"].form
            else:
                replace_edge(conj, new_spec_list=[cur_form], replace_deprel=True)


def conjoined_subj(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, "gov_new", [
            [
                Restriction({"gov": "^((?!root|case|nsubj|dobj).)*$", "name": "gov", "nested": [
                    [
                        Restriction({"gov": "rcmod"}),
                        Restriction({"gov": ".*conj.*", "name": "dep", "diff": ["gov_new"]})
                    ],
                    [
                        Restriction({"gov": ".*conj.*", "name": "dep", "diff": ["gov_new"], "nested": [[Restriction({"gov": "rcmod"})]]})
                    ]
                ]})
            ],
            [
                Restriction({"gov": "^((?!root|case).)*$", "name": "gov", "nested": [[
                    Restriction({"no-gov": "rcmod"}),
                    Restriction({"gov": ".*conj.*", "name": "dep", "diff": ["gov_new"], "nested": [[Restriction({"no-gov": "rcmod"})]]})
                ]]})
            ]])
            
        if not is_matched:
            continue
        
        add_edge(ret['dep'], ret['gov']['conllu_info'].deprel, head=ret['gov']['conllu_info'].head)


def conjoined_verb(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [[
            Restriction({"gov": "conj", "name": "conj", "nested": [[
                Restriction({"no-gov": ".subj"})
            ]]}),
            Restriction({"gov": ".subj", "name": "subj"})
        ]])
        
        if not is_matched:
            continue
        
        add_edge(ret['subj'], ret['subj']['conllu_info'].deprel, head=ret['conj']['conllu_info'].id)


def convert_sentence(sentence):
    global tag_counter
    tag_counter = 0
    
    # correctDependencies - correctSubjPass
    correct_subj_pass(sentence)
    
    # addCaseMarkerInformation
    used_cases = []
    passive_agent(sentence)
    prep_patterns(sentence, used_cases, mw3=True)
    prep_patterns(sentence, used_cases, mw2=True)
    prep_patterns(sentence, used_cases)
    if not enhance_only_nmods:
        prep_patterns(sentence, used_cases, mw3=True, fix_nmods=False)
        prep_patterns(sentence, used_cases, mw2=True, fix_nmods=False)
        prep_patterns(sentence, used_cases, fix_nmods=False)
    
    # addConjInformation
    conj_info(sentence)
    
    # treatCC
    conjoined_subj(sentence)
    conjoined_verb(sentence) # TODO - finish
    
    # TODO - continue conversion
    return sentence


def convert(parsed):
    converted_sentences = []
    for sentence in parsed:
        converted_sentences.append(convert_sentence(sentence))
    return converted_sentences

