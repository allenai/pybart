# conversions as been done by StanfordConverter (a.k.a SC) version TODO
# global nuances from their converter:
#   1. we always write to 'deps' (so at first we copy 'head'+'deprel' to 'deps'), while they sometimes write back to 'deprel'.
#   2. we think like a multi-graph, so we operate on every relation/edge between two nodes, while they on first one found.
#   3. we look for all fathers as we can have multiple fathers, while in SC they look at first one found.

import regex as re

from matcher import match, Restriction
import configuration as conf

# constants
two_word_preps_regular = ["across_from", "along_with", "alongside_of", "apart_from", "as_for", "as_from", "as_of", "as_per", "as_to", "aside_from", "based_on", "close_by", "close_to", "contrary_to", "compared_to", "compared_with", " depending_on", "except_for", "exclusive_of", "far_from", "followed_by", "inside_of", "irrespective_of", "next_to", "near_to", "off_of", "out_of", "outside_of", "owing_to", "preliminary_to", "preparatory_to", "previous_to", "prior_to", "pursuant_to", "regardless_of", "subsequent_to", "thanks_to", "together_with"]
two_word_preps_complex = ["apart_from", "as_from", "aside_from", "away_from", "close_by", "close_to", "contrary_to", "far_from", "next_to", "near_to", "out_of", "outside_of", "pursuant_to", "regardless_of", "together_with"]
three_word_preps = ["by_means_of", "in_accordance_with", "in_addition_to", "in_case_of", "in_front_of", "in_lieu_of", "in_place_of", "in_spite_of", "on_account_of", "on_behalf_of", "on_top_of", "with_regard_to", "with_respect_to"]
clause_relations = ["conj", "xcomp", "ccomp", "acl", "advcl", "acl:relcl", "parataxis", "appos", "list"]
quant_mod_3w = "(?i:lot|assortment|number|couple|bunch|handful|litany|sheaf|slew|dozen|series|variety|multitude|wad|clutch|wave|mountain|array|spate|string|ton|range|plethora|heap|sort|form|kind|type|version|bit|pair|triple|total)"
quant_mod_2w = "(?i:lots|many|several|plenty|tons|dozens|multitudes|mountains|loads|pairs|tens|hundreds|thousands|millions|billions|trillions|[0-9]+s)"
quant_mod_2w_det = "(?i:some|all|both|neither|everyone|nobody|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|billion|trillion|[0-9]+)"
relativizing_word_regex = "(?i:that|what|which|who|whom|whose)"


# This method corrects subjects of verbs for which we identified an auxpass,
# but didn't identify the subject as passive.
# (includes nsubj/csubj/nsubj:xsubj/csubj:xsubj)
def correct_subj_pass(sentence):
    restriction_lists = [[Restriction(nested=[[
            Restriction(gov='auxpass'),
            # the SC regex (which was "^(nsubj|csubj).*$") was changed here
            # to avoid the need to filter .subjpass relations in the graph-rewriting part
            Restriction(gov="^(.subj|.subj:xsubj)$", name="subj")
        ]])
    ]]
    
    ret = match(sentence.values(), restriction_lists)
    if not ret:
        return
    
    # rewrite graph: for every subject add a 'pass' and replace in graph node
    for name_space in ret:
        subj, subj_head, subj_rel = name_space['subj']
        substitute_rel = re.sub("subj", "subjpass", subj_rel)
        # in SC they add it to the 'deprel' even if the edge was found in the 'deps' :O
        subj.replace_edge(subj_rel, substitute_rel, subj_head, subj_head)


# add 'agent' to nmods if it is cased by 'by', and have an auxpass sibling
def passive_agent(sentence):
    restriction = Restriction(name="gov", nested=[[
        Restriction(gov='auxpass'),
        Restriction(name="mod", gov="nmod", nested=[[
            Restriction(gov='case', form="^(?i:by)$")
        ]])
    ]])

    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return

    # rewrite graph: for every nmod add ':agent' to the graph node relation
    for name_space in ret:
        gov, _, _ = name_space['gov']
        mod, _, mod_rel = name_space['mod']
        mod.replace_edge(mod_rel,  mod_rel + ":agent", gov, gov)


# we need to create a concat string for every marker neighbor chain
# actually it should never happen that they are separate, but nonetheless we add relation if so,
# this might result in multi-graph
# e.g 'in front of' should be [in_front_of] if they are all sequential, but [in, front_of],
# if only 'front' and 'of' are sequential (and 'in' is separated).
def concat_sequential_tokens(c1, c2, c3):
    # add the first word
    sequences = [c1.get_conllu_field('form')]
    prev = c1
    if not c2:
        # we return here because if c2 is None, c3 must be as well
        return sequences
    
    for ci in [c2, c3]:
        # concat every following marker, or start a new string if not
        if prev.get_conllu_field('id') == ci.get_conllu_field('id') - 1:
            sequences[-1] += '_' + ci.get_conllu_field('form')
        else:
            sequences.append(ci.get_conllu_field('form'))
        prev = ci
    return sequences


def prep_patterns(sentence, first_gov, second_gov):
    restriction_lists = \
    [[
        Restriction({"name": "gov", "nested":
        [[
            Restriction({"gov": first_gov, "name": "mod", "nested":
            [[
                Restriction({"gov": second_gov, "name": "c1", "nested":
                [[
                    Restriction({"gov": 'mwe', "name": "c2"}),
                    Restriction({"gov": 'mwe', "name": "c3", "diff": "c2"})
                ]]})
            ],
            [
                Restriction({"gov": second_gov, "name": "c1", "nested":
                    [[
                        Restriction({"gov": 'mwe', "name": "c2"}),
                    ]]})
            ],
            [
                Restriction({"gov": second_gov, "name": "c1", "form": "(?!(^(?i:by)$))."})
            ]]})
        ]]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    for matched in ret:
        mod, mod_head, mod_rel = matched['mod']
        c1, _, _ = matched['c1']
        c2, _, _ = matched['c2'] if 'c2' in matched else (None, None, None)
        c3, _, _ = matched['c3'] if 'c3' in matched else (None, None, None)
    
        sequences = concat_sequential_tokens(c1, c2, c3)
        mod.remove_edge(mod_rel, mod_head)
        for prep_sequence in sequences:
            mod.add_edge(mod_rel + ":" + prep_sequence.lower(), mod_head)


# Adds the type of conjunction to all conjunct relations
def conj_info(sentence):
    restriction_lists = \
    [[
        Restriction({"nested":
        [[
            Restriction({"gov": "cc", "name": "cc"}),
            Restriction({"gov": "^conj$", "name": "conj"})
        ]]})
    ]]
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    # this was added to get the first cc, because it should be applied on all conj's that precedes it
    cur_form = sorted([(triplet[0].get_conllu_field('id'), triplet) for triplet in ret["cc"]])[0][1][0].get_conllu_field('form')
    for (_, (cc_or_conj_source, cc_or_conj_head, cc_or_conj_rel)) in \
            sorted([(triplet[0].get_conllu_field('id'), triplet) for triplet in ret["cc"] + ret["conj"]]):
        if cc_or_conj_rel == "cc":
            cur_form = cc_or_conj_source.get_conllu_field('form')
        else:
            cc_or_conj_source.replace_edge(
                cc_or_conj_rel, cc_or_conj_rel + ":" + cur_form, cc_or_conj_head, cc_or_conj_head)


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
        for obj_source, _, _ in ret['obj']:
            for _, dep_head, _ in ret['dep']:
                if dep_head not in obj_source.get_parents():
                    obj_source.add_edge("nsubj:xsubj", dep_head)
    else:
        for subj_source, _, _ in ret['subj']:
            for _, dep_head, _ in ret['dep']:
                if dep_head not in subj_source.get_parents():
                    subj_source.add_edge("nsubj:xsubj", dep_head)


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


def create_mwe(words, head, rel):
    for i, word in enumerate(words):
        word.remove_all_edges()
        word.add_edge(rel, head)
        if 0 == i:
            head = word
            rel = "mwe"


def is_prep_seq(words, preps):
    return "_".join([word.get_conllu_field('form') for word in words]) in preps


def reattach_children(old_head, new_head):
    # store them before we make change to the original list
    for child in list(old_head.get_children()):
        # this is only for the multi-graph case
        for child_head, child_rel in list(child.get_new_relations(given_head=old_head)):
            child.replace_edge(child_rel, child_rel, old_head, new_head)


def split_concats_by_index(prep_list, prep_len):
    out = list()
    for i in range(prep_len):
        out.append("|".join([prep.split("_")[i] for prep in prep_list]))
    return out


# for example The street is across from you.
# The following relations:
#   advmod(you-6, across-4)
#   case(you-6, from-5)
# would be replaced with:
#   case(you-6, across-4)
#   mwe(across-4, from-5)
def process_simple_2wp(sentence):
    forms = split_concats_by_index(two_word_preps_regular, 2)
    
    restriction_lists = Restriction(nested=[[
        Restriction(gov="(case|advmod)", no_sons_of=".*", name="w1", form="^" + forms[0] + "$"),
        Restriction(gov="case", no_sons_of=".*", follows="w1", name="w2", form="^" + forms[1] + "$")
    ]])
    ret = match(sentence.values(), [[restriction_lists]])
    if not ret:
        return
    
    for name_space in ret:
        w1, w1_head, w1_rel = name_space['w1']
        w2, w2_head, w2_rel = name_space['w2']
        
        # check if words really form a prepositional phrase
        if not is_prep_seq([w1, w2], two_word_preps_regular):
            continue
        
        # create multi word expression
        create_mwe([w1, w2], w1_head, "case")


# for example: He is close to me.
# The following relations:
#   nsubj(close-3, He-1)
#   cop(close-3, is-2)
#   root(ROOT-0, close-3)
#   case(me-6, to-4)
#   nmod(close-3, me-6)
# would be replaced with:
#   nsubj(me-6, He-1)
#   cop(me-6, is-2)
#   case(me-6, close-3)
#   mwe(close-3, to-4)
#   root(ROOT-0, me-6)
def process_complex_2wp(sentence):
    forms = split_concats_by_index(two_word_preps_complex, 2)

    inner_rest = Restriction(gov="nmod", name="gov2", nested=[[
        Restriction(name="w2", no_sons_of=".*", form="^" + forms[1] + "$")
    ]])
    restriction_lists = Restriction(name="gov", nested=[[
        Restriction(name="w1", followed_by="w2", form="^" + forms[0] + "$", nested=[
            [inner_rest, Restriction(name="cop", gov="cop")],
            [inner_rest]
        ])
    ]])
    
    ret = match(sentence.values(), [[restriction_lists]])
    if not ret:
        return

    for name_space in ret:
        w1, _, w1_rel = name_space['w1']
        w2, _, _ = name_space['w2']
        gov, _, _ = name_space['gov']
        gov2, _, gov2_rel = name_space['gov2']
        cop, _, _ = name_space['cop'] if "cop" in name_space else (None, None, None)
        
        # check if words really form a prepositional phrase
        if not is_prep_seq([w1, w2], two_word_preps_complex):
            continue
        
        # Determine the relation to use for gov2's governor
        if (w1_rel == "root") or (cop and (w1_rel in clause_relations)):
            gov2.replace_edge(gov2_rel, w1_rel, w1, gov)
        else:
            gov2.replace_edge(gov2_rel, gov2_rel, w1, gov)
        
        # reattach w1 sons to gov2.
        reattach_children(w1, gov2)
        
        # create multi word expression
        create_mwe([w1, w2], gov2, "case")


# for example: He is close to me.
# The following relations:
#   nsubj(front-4, I-1)
#   cop(front-4, am-2)
#   case(front-4, in-3)
#   root(ROOT-0, front-4)
#   case(you-6, of-5)
#   nmod(front-4, you-6)
# would be replaced with:
#   nsubj(you-6, I-1)
#   cop(you-6, am-2)
#   case(you-6, in-3)
#   mwe(in-3, front-4)
#   mwe(in-3, of-5)
#   root(ROOT-0, you-6)
def process_3wp(sentence):
    forms = split_concats_by_index(three_word_preps, 3)
    
    restriction_lists = Restriction(name="gov", nested=[[
        Restriction(name="w2", followed_by="w3", follows="w1", form="^" + forms[1] + "$", nested=[[
            Restriction(name="gov2", gov="(nmod|acl|advcl)", nested=[[
                Restriction(name="w3", gov="(case|mark)", no_sons_of=".*", form="^" + forms[2] + "$")
            ]]),
            Restriction(name="w1", gov="^(case)$", no_sons_of=".*", form="^" + forms[0] + "$")
        ]])
    ]])
    
    ret = match(sentence.values(), [[restriction_lists]])
    if not ret:
        return
    
    for name_space in ret:
        w1, _, _ = name_space['w1']
        w2, _, w2_rel = name_space['w2']
        w3, _, _ = name_space['w3']
        gov, _, _ = name_space['gov']
        gov2, _, gov2_rel = name_space['gov2']
        
        # check if words really form a prepositional phrase
        if not is_prep_seq([w1, w2, w3], three_word_preps):
            continue
        
        # Determine the relation to use
        if (w2_rel == "nmod") and (gov2_rel in ["acl", "advcl"]):
            gov2.replace_edge(gov2_rel, gov2_rel, w2, gov)
            case = "mark"
        else:
            gov2.replace_edge(gov2_rel, w2_rel, w2, gov)
            case = "case"

        # reattach w2 sons to gov2
        reattach_children(w2, gov2)
        
        # create multi word expression
        create_mwe([w1, w2, w3], gov2, case)


# The following two methods corrects Partitives and light noun constructions,
# by making it a multi word expression with head of det:qmod.
# for example: A couple of people.
# The following relations:
#   det(couple-2, A-1)
#   root(ROOT-0, couple-2)
#   case(people-4, of-3)
#   nmod(couple-2, people-4)
# would be replaced with:
#   det:qmod(people-4, A-1)
#   mwe(A-1, couple-2,)
#   mwe(A-1, of-3)
#   root(ROOT-0, people-4)
def demote_per_type(sentence, rl):
    ret = match(sentence.values(), [[rl]])
    if not ret:
        return

    for name_space in ret:
        old_gov, old_gov_head, old_gov_rel = name_space['w1']
        w2, w2_head, w2_rel = name_space['w2']
        gov2, _, gov2_rel = name_space['gov2']
        
        words = [old_gov, w2]
        if 'w3' in name_space:
            w3, _, _ = name_space['w3']
            words += [w3]
            # run over what we 'though' to be the old_gov, as this is a 3-word mwe
            old_gov, old_gov_head, old_gov_rel = name_space['w2']
        elif 'det' in name_space:
            # NOTE: this is not done in SC, but should have been by THE PAPER.
            # adding the following determiner to the mwe.
            det, _, _ = name_space['det']
            words += [det]
        
        gov2.replace_edge(gov2_rel, old_gov_rel, old_gov, old_gov_head)
        create_mwe(words, gov2, "det:qmod")


def demote_quantificational_modifiers(sentence):
    quant_3w = Restriction(nested=[[
        Restriction(name="w2", no_sons_of="amod", form=quant_mod_3w, followed_by="w3", nested=[[
            Restriction(name="w1", gov="det", form="(?i:an?)"),
            Restriction(name="gov2", gov="nmod", xpos="(NN.*|PRP.*)", nested=[[
                Restriction(name="w3", gov="case", form="(?i:of)")
            ]])
        ]])
    ]])
    
    quant_2w = Restriction(nested=[[
        Restriction(name="w1", form=quant_mod_2w, followed_by="w2", nested=[[
            Restriction(name="gov2", gov="nmod", xpos="(NN.*|PRP.*)", nested=[[
                Restriction(name="w2", gov="case", form="(?i:of)")
            ]])
        ]])
    ]])
    
    quant_2w_det = Restriction(nested=[[
        Restriction(name="w1", form=quant_mod_2w_det, followed_by="w2", nested=[
            [Restriction(name="gov2", gov="nmod", xpos="(NN.*)", nested=[[
                Restriction(name="det", gov="det"),
                Restriction(name="w2", gov="case", form="(?i:of)", followed_by="det")
            ]])
        ],
            [Restriction(name="gov2", gov="nmod", xpos="(PRP.*)", nested=[[
                Restriction(name="w2", gov="case", form="(?i:of)")
            ]])
        ]])
    ]])
    
    for rl in [quant_3w, quant_2w, quant_2w_det]:
        demote_per_type(sentence, rl)
 

def add_ref_and_collapse(sentence):
    child_rest = Restriction({"name": "child_ref", "form": relativizing_word_regex})
    grandchild_rest = \
        Restriction({"nested":
            [[
                Restriction({"name": "grand_ref", "form": relativizing_word_regex})
            ]]})
    restriction_lists = \
    [[
        Restriction({"name": "gov", "nested":
        [[
            Restriction({"gov": 'acl:relcl', "nested":
            [
                [grandchild_rest, child_rest],
                [grandchild_rest],
                [child_rest]
            ]}),
        ]]})
    ]]
    
    ret = dict()
    if not match(sentence.values(), restriction_lists, ret):
        return
    
    for gov, gov_head, gov_rel in ret['gov']:
        leftmost = None
        descendants = ([d for d, _, _ in ret['grand_ref']] if 'grand_ref' in ret else []) + \
                     ([d for d, _, _ in ret['child_ref']] if 'child_ref' in ret else [])
        for descendant in descendants:
            if (not leftmost) or descendant.get_conllu_field('id') < leftmost.get_conllu_field('id'):
                leftmost = descendant
        
        for parent, edge in leftmost.get_new_relations():
            leftmost.remove_edge(edge, parent)
            gov.add_edge(edge, parent)
        
        leftmost.add_edge("ref", gov)


def assign_ccs_to_conjs(ret):
    cc_assignments = []
    ccs = []
    conjs = []
    for name_space in ret:
        ccs.append((name_space['cc'][0].get_conllu_field('id'), name_space['cc']))
        conjs.append((name_space['conj'][0].get_conllu_field('id'), name_space['conj']))
    sorted_ccs_and_conjs = sorted(ccs + conjs)
    _, cur_cc = sorted(ccs)[0]
    for _, (cc_or_conj, head, rel) in sorted_ccs_and_conjs:
        if rel == "cc":
            cur_cc = (cc_or_conj, head, rel)
        else:
            cc_assignments.append(((cc_or_conj, head, rel), cur_cc))
    return cc_assignments


# The label of the conjunct relation includes the conjunction type
# because if the verb has multiple cc relations then it can be impossible
# to infer which coordination marker belongs to which conjuncts.
def expand_per_type(sentence, restriction, is_pp):
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    # assign ccs to conjs according to precedence
    cc_assignments = assign_ccs_to_conjs(ret)
    
    nodes_copied = 0
    last_copy_id = -1
    for name_space in ret:
        gov, _, gov_rel = name_space['gov']
        to_copy, _, _ = name_space['to_copy']
        cc, cc_head, cc_rel = name_space['cc']
        conj, conj_head, conj_rel = name_space['conj']
        
        if ((conj, conj_head, conj_rel), (cc, cc_head, cc_rel)) not in cc_assignments:
            continue
        
        # create a copy node,
        # add conj:cc_info('to_copy', copy_node)
        nodes_copied = 1 if to_copy.get_conllu_field('id') != last_copy_id else nodes_copied + 1
        last_copy_id = to_copy.get_conllu_field('id')
        new_id = to_copy.get_conllu_field('id') + (0.1 * nodes_copied)
        copy_node = to_copy.copy(
            new_id=new_id,
            head="_",
            deprel="_",
            misc="CopyOf=%d" % to_copy.get_conllu_field('id'))
        copy_node.add_edge("conj:" + cc.get_conllu_field('form'), to_copy)
        sentence[new_id] = copy_node
        
        if is_pp:
            # replace cc('gov', 'cc') with cc('to_copy', 'cc')
            # NOTE: this is not mentioned in THE PAPER, but is done in SC (and makes sense).
            cc.replace_edge(cc_rel, cc_rel, cc_head, to_copy)
            
            # replace conj('gov', 'conj') with e.g nmod(copy_node, 'conj')
            conj.replace_edge(conj_rel, gov_rel, conj_head, copy_node)
        else:
            # copy relation from modifier to new node e.g nmod:from(copy_node, 'modifier')
            modifier, _, modifier_rel = name_space['modifier']
            modifier.add_edge(modifier_rel + ":" + conj.get_conllu_field('form'), copy_node)


# Expands PPs with conjunctions such as in the sentence
# "Bill flies to France and from Serbia." by copying the verb
# that governs the prepositional phrase resulting in the following new or changed relations:
#   conj:and(flies, flies')
#   cc(flies, and)
#   nmod(flies', Serbia)
# while those where removed:
#   cc(France-4, and-5)
#   conj(France-4, Serbia-7)
# After that, expands prepositions with conjunctions such as in the sentence
# "Bill flies to and from Serbia." by copying the verb resulting
# in the following new relations:
#   conj:and(flies, flies')
#   nmod(flies', Serbia)
def expand_pp_or_prep_conjunctions(sentence):
    pp_restriction = Restriction(name="to_copy", nested=[[
        Restriction(name="gov", gov="^(nmod|acl|advcl)$", nested=[[
            Restriction(gov="case"),
            Restriction(name="cc", gov="cc"),
            Restriction(name="conj", gov="conj", nested=[[
                Restriction(gov="case")
            ]])
        ]])
    ]])
    
    prep_restriction = Restriction(name="to_copy", nested=[[
        Restriction(name="modifier", nested=[[
            Restriction(name="gov", gov="case", nested=[[
                Restriction(name="cc", gov="cc"),
                Restriction(name="conj", gov="conj")
            ]])
        ]])
    ]])
    
    for rl, is_pp in [(pp_restriction, True), (prep_restriction, False)]:
        expand_per_type(sentence, rl, is_pp)


def convert_sentence(sentence):
    # correctDependencies - correctSubjPass, processNames and removeExactDuplicates.
    # the last two have been skipped. processNames for future decision, removeExactDuplicates for redundancy.
    correct_subj_pass(sentence)

    if conf.enhanced_plus_plus:
        # processMultiwordPreps: processSimple2WP, processComplex2WP, process3WP
        process_simple_2wp(sentence)
        process_complex_2wp(sentence)
        process_3wp(sentence)
        # demoteQuantificationalModifiers
        demote_quantificational_modifiers(sentence)
        # add copy nodes: expandPPConjunctions, expandPrepConjunctions
        expand_pp_or_prep_conjunctions(sentence)
    
    # addCaseMarkerInformation
    passive_agent(sentence)
    # prep_patterns(sentence, '^nmod$', 'case')
    # if not conf.enhance_only_nmods:
    #     prep_patterns(sentence, '^(advcl|acl)$', '^(mark|case)$')
    #
    # # addConjInformation
    # conj_info(sentence)
    #
    # # referent: addRef, collapseReferent
    # if conf.enhanced_plus_plus:
    #     add_ref_and_collapse(sentence)
    #
    # # treatCC
    # conjoined_subj(sentence)
    # conjoined_verb(sentence)
    #
    # # addExtraNSubj
    # xcomp_propagation(sentence)

    # correctSubjPass
    correct_subj_pass(sentence)

    return sentence


def convert(parsed):
    converted_sentences = []
    for sentence in parsed:
        converted_sentences.append(convert_sentence(sentence))
    return converted_sentences
