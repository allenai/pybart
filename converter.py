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
enhanced_plus_plus = True

# global states
tag_counter = 0

# constants
two_word_preps_regular = ["across_from", "along_with", "alongside_of", "apart_from", "as_for", "as_from", "as_of", "as_per", "as_to", "aside_from", "based_on", "close_by", "close_to", "contrary_to", "compared_to", "compared_with", " depending_on", "except_for", "exclusive_of", "far_from", "followed_by", "inside_of", "irrespective_of", "next_to", "near_to", "off_of", "out_of", "outside_of", "owing_to", "preliminary_to", "preparatory_to", "previous_to", " prior_to", "pursuant_to", "regardless_of", "subsequent_to", "thanks_to", "together_with"]


class Restriction(object):
        def __init__(self, dictionary):
            self._dictionary = {"name": None, "gov": None, "no-gov": None, "diff": None, "form": None, "xpos": None, "nested": None}
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
            named_nodes[cur_name] = [sent[cur_id]]
        
        one_restriction_violated = False
        for restriction in restriction_list:
            # first validate the restriction is not None,
            # this might happen if we build CONDITIONED restrictions.
            if not restriction:
                continue
            
            # this is separated, because this is the only restriction type that should be met on all kids
            if restriction["no-gov"]:
                if False in [re.match(restriction["no-gov"], child['conllu_info'].deprel) is None for child in sent[cur_id]['children_list']]:
                    break

            restriction_matched = False
            for child in sent[cur_id]['children_list']:
                inner_named_nodes = {}
                
                if restriction["gov"]:
                    if not re.match(restriction["gov"], child['conllu_info'].deprel):
                        continue
                
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
                
                if restriction["xpos"]:
                    if not re.match(restriction["xpos"], child['conllu_info'].xpos):
                        continue
                
                if restriction["name"]:
                    if restriction["name"] not in named_nodes:
                        named_nodes[restriction["name"]] = [child]
                    else:
                        named_nodes[restriction["name"]] += [child]
     
                named_nodes.update(inner_named_nodes)
                restriction_matched = True
            
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
        cw.replace_conllu_info(node, deprel=rel_with_specs, head=head)
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
            Restriction({"gov": "^(nsubj|csubj)$", "name": "subj"})
        ]])
        if not is_matched:
            continue
        
        for subj in ret['subj']:
            replace_edge(subj, new_rel=re.sub("subj", "subjpass", subj['conllu_info'].deprel), replace_deprel=True)


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
        
        for mod in ret['mod']:
            replace_edge(mod, new_spec_list=["agent"], replace_deprel=True)


def prep_patterns(sentence, fix_nmods=True):
    # to enhance nmods or acl/advcls markers
    if fix_nmods:
        first_gov = '^nmod$'
        second_gov = 'case'
    else:
        first_gov = '^(advcl|acl)$'
        second_gov = '^(mark|case)$'
    
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [
        [
            Restriction({"gov": first_gov, "name": "mod", "nested": [[
                Restriction({"gov": second_gov, "name": "c1", "nested": [[
                    Restriction({"gov": 'mwe', "name": "c2"})
                ]]})
            ]]})
        ],
        [
            Restriction({"gov": first_gov, "name": "mod", "nested": [[
                Restriction({"gov": second_gov, "name": "c1", "form": "(?!(^(?i:by)$))."})
            ]]})
        ]])
        
        # We only want to match every case/marker once, so we test, and save them for further propagation
        # TODO - maybe a nicer and clearer way to do this?
        if not is_matched:
            continue
        
        for mod in ret['mod']:
            for c1 in ret['c1']:
                strs_to_add = [c1['conllu_info'].form]
                if 'c2' in ret:
                    # we need to create a concat string for every marker neighbor chain
                    # actually it should never happen that they are separate, but nonetheless we add relation if so,
                    # as done in the stanford converter code
                    prev = c1
                    for c2 in ret['c2']:
                        if prev['conllu_info'].id == c2['conllu_info'].id - 1:
                            strs_to_add[-1] += '_' + c2['conllu_info'].form
                        else:
                            strs_to_add.append(c2['conllu_info'].form)
                        prev = c2
                
                replace_edge(
                    mod,
                    new_spec_list=strs_to_add,
                    replace_deprel=False if len(strs_to_add) > 1 else True)


def conj_info(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [[
            Restriction({"gov": "cc", "name": "cc"}),
            Restriction({"gov": "conj", "name": "conj"})
        ]])
        if not is_matched or "cc" not in ret or "conj" not in ret:
            continue
        
        cur_form = None
        for (_, cc_or_conj) in sorted([(node["conllu_info"].id, node) for node in ret["cc"] + ret["conj"]]):
            if cc_or_conj["conllu_info"].deprel == "cc":
                cur_form = cc_or_conj["conllu_info"].form
            else:
                replace_edge(cc_or_conj, new_spec_list=[cur_form], replace_deprel=True)


def conjoined_subj(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, "gov_new", [
            [
                Restriction({"gov": "^((?!root|case|nsubj|dobj).)*$", "name": "gov", "nested": [
                    [
                        # TODO - I don't fully understand why SC decided to add this rcmod condition, and I belive they have a bug:
                        #   (rcmodHeads.contains(gov) && rcmodHeads.contains(dep)) should be ||, and so I coded.
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
        
        for gov in ret['gov']:
            for dep in ret['dep']:
                add_edge(dep, gov['conllu_info'].deprel, head=gov['conllu_info'].head)


def conjoined_verb(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [
        [
            Restriction({"gov": "conj", "name": "conj", "xpos": "(VB|JJ)", "nested": [[
                Restriction({"no-gov": ".subj"}),
                Restriction({"gov": "auxpass", "name": "auxpass"})
            ]]}),
            Restriction({"gov": ".subj", "name": "subj"})
        ],
        [
            Restriction({"gov": "conj", "name": "conj", "xpos": "(VB|JJ)", "nested": [[
                Restriction({"no-gov": ".subj|auxpass"})
            ]]}),
            Restriction({"gov": ".subj", "name": "subj"})
        ]])
        
        if not is_matched:
            continue
        
        for subj in ret['subj']:
            for conj in ret['conj']:
                # fixing the relation as done in SC
                relation = subj['conllu_info'].deprel
                if relation == "nsubjpass":
                    if subj['conllu_info'].xpos in ["VB", "VBZ", "VBP", "JJ"]:
                        relation = "nsubj"
                elif relation == "csubjpass":
                    if subj['conllu_info'].xpos in ["VB", "VBZ", "VBP", "JJ"]:
                        relation = "csubj"
                elif relation == "nsubj":
                    if "auxpass" in ret:
                        relation = "nsubjpass"
                elif relation == "csubj":
                    if "auxpass" in ret:
                        relation = "csubjpass"
                
                add_edge(subj, relation, head=conj['conllu_info'].id)
                # TODO - we need to add the aux relation (as SC say they do but not in the code)
                #   and the obj relation, which they say they do and also coded, but then commented out...


def xcomp_propagation(sentence):
    to_xcomp_rest = \
        [
            Restriction({"gov": "xcomp", "name": "dep", "form": "^(?i:to)$", "nested": [[
                Restriction({"no-gov": "nsubj"}),  # includes both nsubj and nsubj pass but noe csubjs
                Restriction({"no-gov": "^(aux|mark)$"})
            ]]}),
            Restriction({"gov": "nsubj", "name": "subj"}),
        ]
    basic_xcomp_rest = \
         [
            Restriction({"gov": "xcomp", "name": "dep", "form": "(?!(^(?i:to)$)).", "nested": [[
                Restriction({"no-gov": "nsubj"}),  # includes both nsubj and nsubj pass but noe csubjs
                Restriction({"gov": "^(aux|mark)$"})
            ]]}),
            Restriction({"gov": "nsubj", "name": "subj"}),
        ]

    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, None, [
            to_xcomp_rest + [Restriction({"gov": "dobj", "name": "obj"})],
            to_xcomp_rest,
            basic_xcomp_rest + [Restriction({"gov": "dobj", "name": "obj"})],
            basic_xcomp_rest
        ])
        
        if not is_matched:
            continue
        
        if 'obj' in ret:
            for obj in ret['obj']:
                if ret['dep']['conllu_info'].head not in obj['new_deps'][1].keys():
                    add_edge(obj, obj['conllu_info'].deprel, head=ret['dep']['conllu_info'].head)
        else:
            for subj in ret['subj']:
                if ret['dep']['conllu_info'].head not in subj['new_deps'][1].keys():
                    add_edge(subj, subj['conllu_info'].deprel, head=ret['dep']['conllu_info'].head)


def process_multiword_preps(sentence):
    for (cur_id, token) in sentence.items():
        is_matched, ret = match(sentence, cur_id, "gov", [[
            Restriction({"gov": "case", "name": "case", "nested": [[
                Restriction({"no-gov": ".*"})
            ]]}),
            Restriction({"gov": "advmod", "name": "advmod", "nested": [[
                Restriction({"no-gov": ".*"})
            ]]})

        ]])
        
        if (not is_matched) or ('case' not in ret):
            continue
        
        if 'advmod' in ret:
            for advmod in ret['advmod']:
                for case in ret['case']:
                    if (advmod['conllu_info'].id == case['conllu_info'].id - 1) and \
                            ((advmod['conllu_info'].form + "_" + case['conllu_info'].form) in two_word_preps_regular):
                        add_edge(advmod, "case", replace_deprel=True)
                        add_edge(case, "mwe", head=ret['gov']['conllu_info'].id, replace_deprel=True)
        for case1 in ret['case']:
            for case2 in ret['case']:
                if (case1['conllu_info'].id == case2['conllu_info'].id - 1) and \
                        ((case1['conllu_info'].form + "_" + case2['conllu_info'].form) in two_word_preps_regular):
                    add_edge(case1, "case", replace_deprel=True)
                    add_edge(case2, "mwe", head=ret['gov']['conllu_info'].id, replace_deprel=True)


def convert_sentence(sentence):
    global tag_counter
    tag_counter = 0
    
    # correctDependencies - correctSubjPass, processNames and removeExactDuplicates.
    # the last two have been skipped. processNames for future decision, removeExactDuplicates for redundancy.
    correct_subj_pass(sentence)
    
    # processMultiwordPreps
    if enhanced_plus_plus:
        process_multiword_preps(sentence)
    
    # addCaseMarkerInformation
    passive_agent(sentence)
    prep_patterns(sentence)
    if not enhance_only_nmods:
        prep_patterns(sentence, fix_nmods=False)
    
    # addConjInformation
    conj_info(sentence)
    
    # treatCC
    conjoined_subj(sentence)
    conjoined_verb(sentence)
    
    # addExtraNSubj
    xcomp_propagation(sentence)
    
    # correctSubjPass
    # TODO - why again?
    correct_subj_pass(sentence)
    
    # TODO - continue conversion
    return sentence


def convert(parsed):
    converted_sentences = []
    for sentence in parsed:
        converted_sentences.append(convert_sentence(sentence))
    return converted_sentences

