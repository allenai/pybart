###
# TODO:
#   1. what new_deps should be lowercased and lematization
#   2. more docu!
#   3. recursive (such as conj)
###

import regex as re
import configuration as conf

# global states
tag_counter = 0

# constants
two_word_preps_regular = ["across_from", "along_with", "alongside_of", "apart_from", "as_for", "as_from", "as_of", "as_per", "as_to", "aside_from", "based_on", "close_by", "close_to", "contrary_to", "compared_to", "compared_with", " depending_on", "except_for", "exclusive_of", "far_from", "followed_by", "inside_of", "irrespective_of", "next_to", "near_to", "off_of", "out_of", "outside_of", "owing_to", "preliminary_to", "preparatory_to", "previous_to", " prior_to", "pursuant_to", "regardless_of", "subsequent_to", "thanks_to", "together_with"]
two_word_preps_complex = ["apart_from", "as_from", "aside_from", "away_from", "close_by", "close_to", "contrary_to", "far_from", "next_to", "near_to", "out_of", "outside_of", "pursuant_to", "regardless_of", "together_with"]
three_word_preps = ["by_means_of", "in_accordance_with", "in_addition_to", "in_case_of", "in_front_of", "in_lieu_of", "in_place_of", "in_spite_of", "on_account_of", "on_behalf_of", "on_top_of", "with_regard_to", "with_respect_to"]
clause_relations = ["conj", "xcomp", "ccomp", "acl", "advcl", "acl:relcl", "parataxis", "appos", "list"]


class Restriction(object):
        def __init__(self, dictionary):
            self._dictionary = {"name": None, "gov": None, "no-gov": None, "diff": None,
                                "form": None, "xpos": None, "follows": None, "nested": None}
            self._dictionary.update(dictionary)
        
        def __setitem__(self, key, item):
                if key not in self._dictionary:
                    raise KeyError("The key {} is not defined.".format(key))
                self._dictionary[key] = item
        
        def __getitem__(self, key):
            return self._dictionary[key]


# ----------------------------------------- matching functions ----------------------------------- #

def match(children, restriction_lists, given_named_nodes, additional_named_nodes=None, head=None):
    for restriction_list in restriction_lists:
        named_nodes = dict(given_named_nodes)
        
        one_restriction_violated = False
        for restriction in restriction_list:
            restriction_matched = False
            for child in children:
                if restriction["form"]:
                    if not re.match(restriction["form"], child.get_conllu_field('form')):
                        continue
                
                if restriction["xpos"]:
                    if not re.match(restriction["xpos"], child.get_conllu_field('xpos')):
                        continue
                
                relations = [None]
                if restriction["gov"]:
                    relations = child.match_rel(restriction["gov"], head)
                    if len(relations) == 0:
                        continue
                elif head:
                    relations = child.match_rel(".*", head)
                
                if restriction["no-gov"]:
                    if False in [len(grandchild.match_rel(restriction["no-gov"], child)) == 0 for grandchild in child.get_children()]:
                        continue
                
                # this is not really a restriction, but a feature, adding a name to a node.
                if restriction["nested"]:
                    inner_additional_named_nodes = {
                        **({restriction["name"]: [(child, head, rel) for rel in relations]} if restriction["name"] else {}),
                        **(additional_named_nodes if additional_named_nodes else {})}
                    if not match(
                            child.get_children(),
                            restriction["nested"],
                            named_nodes,
                            additional_named_nodes=inner_additional_named_nodes,
                            head=child):
                        continue
                
                if restriction["follows"]:
                    if restriction["follows"] in named_nodes.keys():
                        if len(named_nodes[restriction["follows"]]) > 1:
                            raise Exception("we never excpect to have someone follow more than one named node")
                        antecedent = named_nodes[restriction["follows"]][0][0]
                        if child.get_conllu_field('id') - 1 != antecedent.get_conllu_field('id'):
                            continue
                    elif restriction["follows"] in additional_named_nodes.keys():
                        if len(additional_named_nodes[restriction["follows"]]) > 1:
                            raise Exception("we never excpect to have someone follow more than one named node")
                        antecedent = additional_named_nodes[restriction["follows"]][0][0]
                        if child.get_conllu_field('id') - 1 != antecedent.get_conllu_field('id'):
                            continue
                    else:
                        raise ValueError("got wrong type of 'follows' restriction")
                
                if restriction["name"]:
                    if restriction["name"] in named_nodes:
                        named_nodes[restriction["name"]] += [(child, head, rel) for rel in relations]
                    else:
                        named_nodes[restriction["name"]] = [(child, head, rel) for rel in relations]
                restriction_matched = True
            
            if not restriction_matched:
                one_restriction_violated = True
                break
        
        if not one_restriction_violated:
            given_named_nodes.update(named_nodes)
            return True
    
    return False
    

# corrects subjs (includes nsubj/csubj/nsubj:xsubj/csubj:xsubj) to subjpass,
# if they are a sibling of auxpass.
def correct_subj_pass(sentence):
    restriction_lists = \
    [[
        Restriction({"nested":
        [[
            Restriction({"gov": 'auxpass'}),
            Restriction({"gov": "^(nsubj|csubj)$", "name": "subj"})
        ]]})
    ]]
    ret = dict()
    
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    for subj_source, subj_head, subj_rel in ret['subj']:
        subj_source.replace_edge(subj_rel, re.sub("subj", "subjpass", subj_rel), subj_head, subj_head)


# add 'agent' to nmods
def passive_agent(sentence):
    restriction_lists = \
    [[
        Restriction({"nested":
        [[
            Restriction({"gov": 'nmod', "name": "mod", "nested":
            [[
                Restriction({"gov": 'case', "form": "^(?i:by)$"})
            ]]}),
            Restriction({"gov": "auxpass"})
        ]]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    for mod_source, mod_head, mod_rel in ret['mod']:
        mod_source.replace_edge(mod_rel,  mod_rel + ":agent", mod_head, mod_head)


def build_strings_to_add(ret):
    strs_to_add = []
    
    for c1_source, _, _ in ret['c1']:
        strs_to_add += [c1_source.get_conllu_field('form')]
        if 'c2' in ret:
            # we need to create a concat string for every marker neighbor chain
            # actually it should never happen that they are separate, but nonetheless we add relation if so,
            # this might result in multi-graph
            prev = c1_source
            for c2_source, _, _ in ret['c2']:
                if prev.get_conllu_field('id') == c2_source.get_conllu_field('id') - 1:
                    strs_to_add[-1] += '_' + c2_source.get_conllu_field('form')
                else:
                    strs_to_add.append(c2_source.get_conllu_field('form'))
                prev = c2_source
    
    return strs_to_add


def prep_patterns(sentence, first_gov, second_gov):
    restriction_lists = \
    [[
        Restriction({"name": "gov", "nested":
        [[
            Restriction({"gov": first_gov, "name": "mod", "nested":
            [[
                Restriction({"gov": second_gov, "name": "c1", "nested":
                [[
                    Restriction({"gov": 'mwe', "name": "c2"})
                ]]})
            ]]})
        ],
        [
            Restriction({"gov": first_gov, "name": "mod", "nested":
            [[
                Restriction({"gov": second_gov, "name": "c1", "form": "(?!(^(?i:by)$))."})
            ]]})
        ]]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    for gov_source, _, _ in ret['gov']:
        for mod_source, mod_head, mod_rel in ret['mod']:
            strs_to_add = build_strings_to_add(ret)
            mod_source.remove_edge(mod_rel, mod_head)
            for str_to_add in strs_to_add:
                mod_source.add_edge(mod_rel + ":" + str_to_add.lower(), gov_source)


# Adds the type of conjunction to all conjunct relations
def conj_info(sentence):
    restriction_lists = \
    [[
        Restriction({"nested":
        [[
            Restriction({"gov": "cc", "name": "cc"}),
            Restriction({"gov": "conj", "name": "conj"})
        ]]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    cur_form = None
    for (_, (cc_or_conj_source, cc_or_conj_head, cc_or_conj_rel)) in sorted([(triplet[0].get_conllu_field('id'), triplet) for triplet in ret["cc"] + ret["conj"]]):
        if cc_or_conj_rel == "cc":
            cur_form = cc_or_conj_source.get_conllu_field('form')
        else:
            cc_or_conj_source.replace_edge(cc_or_conj_rel, cc_or_conj_rel + ":" + cur_form, cc_or_conj_head, cc_or_conj_head)


def conjoined_subj(sentence):
    restriction_lists = \
    [[
        Restriction({"nested":
        [[
            Restriction({"gov": "^((?!root|case|nsubj|dobj).)*$", "name": "gov", "nested":
            [[
                # TODO - I don't fully understand why SC decided to add this rcmod condition, and I believe they have a bug:
                #   (rcmodHeads.contains(gov) && rcmodHeads.contains(dep)) should be ||, and so I coded.
                Restriction({"gov": "rcmod"}),
                Restriction({"gov": ".*conj.*", "name": "dep"})
            ],
            [
                Restriction({"gov": ".*conj.*", "name": "dep", "nested":
                [[
                    Restriction({"gov": "rcmod"})
                ]]})
            ]]})
        ],
        [
            Restriction({"gov": "^((?!root|case).)*$", "no-gov": "rcmod", "name": "gov", "nested":
            [[
                Restriction({"gov": ".*conj.*", "no-gov": "rcmod", "name": "dep"})
            ]]})
        ]]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    for _, gov_head, gov_rel in ret['gov']:
        for dep_source, _, _ in ret['dep']:
            dep_source.add_edge(gov_rel, gov_head)


def conjoined_verb(sentence):
    restriction_lists = \
    [[
        Restriction({"nested":
        [[
            Restriction({"gov": "conj", "no-gov": ".subj", "name": "conj", "xpos": "(VB|JJ)", "nested":
            [[
                Restriction({"gov": "auxpass", "name": "auxpass"})
            ]]}),
            Restriction({"gov": ".subj", "name": "subj"})
        ],
        [
            Restriction({"gov": "conj", "no-gov": ".subj|auxpass", "name": "conj", "xpos": "(VB|JJ)"}),
            Restriction({"gov": ".subj", "name": "subj"})
        ]]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    for subj_source, _, subj_rel in ret['subj']:
        for conj_source, _, _ in ret['conj']:
            # TODO - this could be out into restrictions, but it would be a huge add-up,
            # so rather stay with this small if statement
            if subj_rel.endswith("subjpass") and \
                            subj_source.get_conllu_field('xpos') in ["VB", "VBZ", "VBP", "JJ"]:
                subj_rel = subj_rel[:-4]
            elif subj_rel.endswith("subj") and "auxpass" in ret:
                subj_rel += "pass"
            
            subj_source.add_edge(subj_rel, conj_source)
            # TODO - we need to add the aux relation (as SC say they do but not in the code)
            #   and the obj relation, which they say they do and also coded, but then commented out...


def xcomp_propagation_per_type(sentence, restriction):
    restriction_lists = \
    [[
        Restriction({"nested":
        [
            restriction + [Restriction({"gov": "dobj", "name": "obj"})],
            restriction
        ]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    if 'obj' in ret:
        for obj_source, _, obj_rel in ret['obj']:
            for _, dep_head, _ in ret['dep']:
                if dep_head.get_conllu_field('id') not in obj_source.get_parents_ids():
                    obj_source.add_edge(obj_rel, dep_head)
    else:
        for subj_source, _, subj_rel in ret['subj']:
            for _, dep_head, _ in ret['dep']:
                if dep_head.get_conllu_field('id') not in subj_source.get_parents_ids():
                    subj_source.add_edge(subj_rel, dep_head)


def xcomp_propagation(sentence):
    to_xcomp_rest = \
        [
            Restriction({"gov": "xcomp", "no-gov": "^(nsubj.*|aux|mark)$", "name": "dep", "form": "^(?i:to)$"}),
            Restriction({"gov": "nsubj.*", "name": "subj"}),
        ]
    basic_xcomp_rest = \
         [
            Restriction({"gov": "xcomp", "no-gov": "nsubj.*", "name": "dep", "form": "(?!(^(?i:to)$)).", "nested":
            [[
                Restriction({"gov": "^(aux|mark)$"})
            ]]}),
            Restriction({"gov": "nsubj.*", "name": "subj"}),
        ]

    for xcomp_restriction in [to_xcomp_rest, basic_xcomp_rest]:
        xcomp_propagation_per_type(sentence, xcomp_restriction)


def process_simple_2wp(sentence):
    for two_word_prep in two_word_preps_regular:
        w1_form, w2_form = two_word_prep.split("_")
        restriction_lists = \
        [[
            Restriction({"name": "gov", "nested":
            [[
                Restriction({"gov": "(case|advmod)", "no-gov": ".*", "name": "w1", "form": "^" + w1_form + "$"}),
                Restriction({"gov": "case", "no-gov": ".*", "follows": "w1", "name": "w2", "form": "^" + w2_form + "$"})
            ]]})
        ]]
        ret = dict()
        if (not match(sentence.values(), restriction_lists, ret)) or ('case' not in ret):
            continue
        
        for gov, _, _ in ret['gov']:
            for (w1, w1_head, w1_rel), (w2, w2_head, w2_rel) in zip(ret['w1'], ret['w2']):
                w1.replace_edge(w1_rel, "case", w1_head, w1_head)
                w2.replace_edge(w2_rel, "mwe", w2_head, w1)


def fix_2wp(ret, gov=None):
    for w1, _, w1_rel in ret['w1']:
        for gov2, gov2_head, gov2_rel in ret['gov2']:
            # reattach w1 sons to gov2
            w1_has_cop_child = False
            gov2.remove_edge(gov2_rel, w1)
            for child in w1.get_children():
                for child_head, child_rel in child.get_new_relations(given_head=w1.get_conllu_field('id')):
                    if child_rel == "cop":
                        w1_has_cop_child = True
                    child.replace_edge(child_rel, child_rel, w1, gov2)
            
            # replace gov2's governor
            if not gov:
                w1.remove_edge("root", None)
                gov2.add_edge("root", None)
            else:
                # Determine the relation to use.
                rel = gov2_rel
                if w1_has_cop_child and (w1_rel in clause_relations):
                    rel = w1_rel
                
                w1.remove_edge(w1_rel, gov)
                gov2.add_edge(rel, gov)
            
            for w2, _, _ in ret['w2']:
                w2.add_edge("case", gov2)
                w1.add_edge("mwe", w2)


def process_complex_2wp(sentence):
    for two_word_prep in two_word_preps_complex:
        w1_form, w2_form = two_word_prep.split("_")
        inner_restriction = \
            Restriction({"name": "w1", "form": "^" + w1_form + "$", "nested":
            [[
                Restriction({"gov": "nmod", "name": "gov2", "nested":
                [[
                    Restriction({"gov": "case", "no-gov": ".*", "name": "w2", "follows": "w1", "form": "^" + w2_form + "$"}),
                ]]}),
            ]]})
        restriction_lists = \
        [
            [Restriction({"name": "gov", "nested": [[inner_restriction]]})],
            [inner_restriction]
        ]
        ret = dict()
        if not match(sentence.values(), restriction_lists, ret):
            continue
        
        if "gov" in ret:
            for gov, _, _ in ret['gov']:
                fix_2wp(ret, gov)
        else:
            fix_2wp(ret)


def fix_3wp(ret, gov=None):
    for w2, _, w2_rel in ret['w2']:
        for gov2, gov2_head, gov2_rel in ret['gov2']:
            # reattach w2 sons to gov2
            gov2.remove_edge(gov2_rel, w2)
            for child in w2.get_children():
                for child_head, child_rel in child.get_new_relations(given_head=w2.get_conllu_field('id')):
                    child.replace_edge(child_rel, child_rel, w2, gov2)
            
            # replace gov2's governor
            case = "case"
            if not gov:
                w2.remove_edge("root", None)
                gov2.add_edge("root", None)
            else:
                # Determine the relation to use. If it is a relation that can
                # join two clauses and w1 is the head of a copular construction,
                # then use the relation of w1 and its parent. Otherwise use the relation of edge.
                rel = w2_rel
                if (w2_rel == "nmod") and (gov2_rel in ["acl", "advcl"]):
                    rel = gov2_rel
                    case = "mark"
                
                w2.remove_edge(w2_rel, gov)
                gov2.add_edge(rel, gov)
            
            for w1, _, _ in ret['w1']:
                w1.add_edge(case, gov2)
                w2.add_edge("mwe", w1)
                for w3, w3_head, w3_rel in ret['w3']:
                    w3.replace_edge(w3_rel, "mwe", w3_head, w1)


def process_3wp(sentence):
    for three_word_prep in three_word_preps:
        w1_form, w2_form, w3_form = three_word_prep.split("_")
        inner_restriction = \
            Restriction({"name": "w2", "follows": "w1", "form": "^" + w2_form + "$", "nested":
            [[
                Restriction({"gov": "(nmod|acl|advcl)", "name": "gov2", "nested":
                [[
                    Restriction({"gov": "(case|mark)", "no-gov": ".*", "name": "w3", "follows": "w2", "form": "^" + w3_form + "$"}),
                ]]}),
                Restriction({"gov": "case", "no-gov": ".*", "name": "w1", "form": "^" + w1_form + "$"})
            ]]})
        restriction_lists = \
        [
            [Restriction({"name": "gov", "nested": [[inner_restriction]]})],
            [inner_restriction]
        ]
        ret = dict()
        if not match(sentence.values(), restriction_lists, ret):
            continue
        
        if "gov" in ret:
            for gov, _, _ in ret['gov']:
                fix_3wp(ret, gov)
        else:
            fix_3wp(ret)


def convert_sentence(sentence):
    global tag_counter
    tag_counter = 0
    
    # correctDependencies - correctSubjPass, processNames and removeExactDuplicates.
    # the last two have been skipped. processNames for future decision, removeExactDuplicates for redundancy.
    correct_subj_pass(sentence)
    
    if conf.enhanced_plus_plus:
        # processMultiwordPreps: processSimple2WP, processComplex2WP, process3WP
        # process_simple_2wp(sentence)
        process_complex_2wp(sentence)
        process_3wp(sentence)
    
    # addCaseMarkerInformation
    passive_agent(sentence)
    prep_patterns(sentence, '^nmod$', 'case')
    if not conf.enhance_only_nmods:
        prep_patterns(sentence, '^(advcl|acl)$', '^(mark|case)$')
    
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
    
    return sentence


def convert(parsed):
    converted_sentences = []
    for sentence in parsed:
        converted_sentences.append(convert_sentence(sentence))
    return converted_sentences
