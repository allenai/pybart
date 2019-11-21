# conversions as been done by StanfordConverter (a.k.a SC) version TODO
# global nuances from their converter:
#   1. we always write to 'deps' (so at first we copy 'head'+'deprel' to 'deps'), while they sometimes write back to 'deprel'.
#   2. we think like a multi-graph, so we operate on every relation/edge between two nodes, while they on first one found.
#   3. we look for all fathers as we can have multiple fathers, while in SC they look at first one found.

import re
from math import copysign

from .matcher import match, Restriction

# constants
nmod_advmod_complex = ["back_to", "back_in", "back_at", "early_in", "late_in", "earlier_in"]
two_word_preps_regular = ["across_from", "along_with", "alongside_of", "apart_from", "as_for", "as_from", "as_of", "as_per", "as_to", "aside_from", "based_on", "close_by", "close_to", "contrary_to", "compared_to", "compared_with", " depending_on", "except_for", "exclusive_of", "far_from", "followed_by", "inside_of", "irrespective_of", "next_to", "near_to", "off_of", "out_of", "outside_of", "owing_to", "preliminary_to", "preparatory_to", "previous_to", "prior_to", "pursuant_to", "regardless_of", "subsequent_to", "thanks_to", "together_with"]
two_word_preps_complex = ["apart_from", "as_from", "aside_from", "away_from", "close_by", "close_to", "contrary_to", "far_from", "next_to", "near_to", "out_of", "outside_of", "pursuant_to", "regardless_of", "together_with"]
three_word_preps = ["by_means_of", "in_accordance_with", "in_addition_to", "in_case_of", "in_front_of", "in_lieu_of", "in_place_of", "in_spite_of", "on_account_of", "on_behalf_of", "on_top_of", "with_regard_to", "with_respect_to"]
clause_relations = ["conj", "xcomp", "ccomp", "acl", "advcl", "acl:relcl", "parataxis", "appos", "list"]
quant_mod_3w = "(?i:lot|assortment|number|couple|bunch|handful|litany|sheaf|slew|dozen|series|variety|multitude|wad|clutch|wave|mountain|array|spate|string|ton|range|plethora|heap|sort|form|kind|type|version|bit|pair|triple|total)"
quant_mod_2w = "(?i:lots|many|several|plenty|tons|dozens|multitudes|mountains|loads|pairs|tens|hundreds|thousands|millions|billions|trillions|[0-9]+s)"
quant_mod_2w_det = "(?i:some|all|both|neither|everyone|nobody|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|billion|trillion|[0-9]+)"
relativizing_word_regex = "(?i:that|what|which|who|whom|whose)"
neg_conjp_prev = ["if_not"]
neg_conjp_next = ["instead_of", "rather_than", "but_rather", "but_not"]
and_conjp_next = ["as_well", "but_also"]
advmod_list = "(here|there|now|later|soon|before|then|today|tomorrow|yesterday|tonight|earlier|early)"
EXTRA_INFO_STUB = 1
g_remove_enhanced_extra_info = False
g_remove_aryeh_extra_info = False


def add_eud_info(orig, extra):
    return orig + ((":" + extra) if not g_remove_enhanced_extra_info else "")


def add_extra_info(orig, dep, iid=None, uncertain=False):
    global g_remove_aryeh_extra_info
    
    if g_remove_aryeh_extra_info:
        return orig
    
    unc = ""
    if uncertain:
        unc = "_unc"
    iid_str = ""
    if iid is not None:
        iid_str = "_id=" + str(iid)
    
    return orig + ":" + dep + "_extra" + unc + iid_str


# This method corrects subjects of verbs for which we identified an auxpass,
# but didn't identify the subject as passive.
# (includes nsubj/csubj/nsubj:xsubj/csubj:xsubj)
def correct_subj_pass(sentence):
    restriction = Restriction(nested=[[
        Restriction(gov='auxpass'),
        # the SC regex (which was "^(nsubj|csubj).*$") was changed here
        # to avoid the need to filter .subjpass relations in the graph-rewriting part
        Restriction(gov="^(.subj|.subj:(?!passive).*)$", name="subj")
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    # rewrite graph: for every subject add a 'pass' and replace in graph node
    for name_space in ret:
        subj, subj_head, subj_rel = name_space['subj']
        substitute_rel = re.sub("(?<!x)subj", "subjpass", subj_rel)
        # in SC they add it to the 'deprel' even if the edge was found in the 'deps' :O
        subj.replace_edge(subj_rel, substitute_rel, subj_head, subj_head)


# add 'agent' to nmods if it is cased by 'by', and have an auxpass sibling
def passive_agent(sentence):
    restriction = Restriction(name="gov", nested=[[
        Restriction(gov='auxpass'),
        Restriction(name="mod", gov="^(nmod)$", nested=[[
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
        mod.replace_edge(mod_rel, add_eud_info(mod_rel, "agent"), gov, gov)


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
    
    for ci in ([c2, c3] if c3 else [c2]):
        if prev.get_conllu_field('id') > ci.get_conllu_field('id'):
            return
        # concat every following marker, or start a new string if not
        elif prev.get_conllu_field('id') == ci.get_conllu_field('id') - 1:
            sequences[-1] += '_' + ci.get_conllu_field('form')
        else:
            sequences.append(ci.get_conllu_field('form'))
        prev = ci
    return sequences


def prep_patterns_per_type(sentence, restriction):
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        mod, mod_head, mod_rel = name_space['mod']
        c1, _, _ = name_space['c1']
        c2, _, _ = name_space['c2'] if 'c2' in name_space else (None, None, None)
        c3, _, _ = name_space['c3'] if 'c3' in name_space else (None, None, None)
        
        sequences = concat_sequential_tokens(c1, c2, c3)
        if not sequences:
            continue
        
        mod.remove_edge(mod_rel, mod_head)
        for prep_sequence in sequences:
            mod.add_edge(add_eud_info(mod_rel, prep_sequence.lower()), mod_head)


def prep_patterns(sentence, first_gov, second_gov):
    restriction_3w = Restriction(name="gov", nested=[[
        Restriction(name="mod", gov=first_gov, nested=[[
            Restriction(name="c1", gov=second_gov, nested=[[
                Restriction(name="c2", gov="mwe"),
                Restriction(name="c3", gov="mwe", diff="c2")
            ]])
        ]])
    ]])
    restriction_2w = Restriction(name="gov", nested=[[
        Restriction(name="mod", gov=first_gov, nested=[[
            Restriction(name="c1", gov=second_gov, nested=[[
                Restriction(name="c2", gov="mwe")
            ]])
        ]])
    ]])
    restriction_1w = Restriction(name="gov", nested=[[
        Restriction(name="mod", gov=first_gov, nested=[[
            # here we want to find any one word that marks a modifier,
            # except cases in which 'by' was used for 'agent' identification,
            # but the 'exact' notation will prevent those from being caught
            Restriction(name="c1", gov=second_gov)
        ]])
    ]])
    
    # NOTE: in SC since they replace the modifier (nmod/advcl/acl) it won't come up again in future matches,
    # as they use the exact (^$) symbols. and so we imitate this behavior.
    for rest in [restriction_3w, restriction_2w, restriction_1w]:
        prep_patterns_per_type(sentence, rest)


def heads_of_conjuncts(sentence):
    restriction = Restriction(name="new_gov", nested=[[
        Restriction(name="gov", gov="^((?!root|case).)*$", nested=[[
             Restriction(name="dep", gov="conj.*")
        ]])
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        gov, gov_head, gov_rel = name_space['gov']
        dep, _, _ = name_space['dep']
        
        # only if the dependant of the conj is not the head of the head of the conj,
        # and they dont fall under the relcl problem, propagate the relation
        # NOTE: actually SC restrict this more aggressively.
        if (gov_head, gov_rel) not in gov.get_extra_info_edges() and gov_head != dep:
            dep.add_edge(gov_rel, gov_head)
        
        # TODO:
        #   for the trees of ambiguous "The boy and the girl who lived told the tale."
        #   we want in the future to add an optional subj relation
        #   P.S. one of the trees could be obtained by the Stanford parser by adding commas:
        #   "The boy and the girl, who lived, told the tale."


# we propagate only subj (for now) as this is what the original code stated:
#     cdm july 2010: This bit of code would copy a dobj from the first
#     clause to a later conjoined clause if it didn't
#     contain its own dobj or prepc. But this is too aggressive and wrong
#     if the later clause is intransitive
#     (including passivized cases) and so I think we have to not have this
#     done always, and see no good "sometimes" heuristic.
#     IF WE WERE TO REINSTATE, SHOULD ALSO NOT ADD OBJ IF THERE IS A ccomp (SBAR).
def subj_of_conjoined_verbs(sentence):
    restriction = Restriction(name="gov", nested=[[
        Restriction(name="conj", gov="conj", no_sons_of=".subj", xpos="(VB|JJ)"),
        Restriction(name="subj", gov=".subj")
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        subj, _, subj_rel = name_space['subj']
        conj, _, _ = name_space['conj']
        
        if subj_rel.endswith("subjpass") and conj.get_conllu_field('xpos') in ["VB", "VBZ", "VBP", "JJ"]:
            subj_rel = subj_rel[:-4]
        elif subj_rel.endswith("subj") and "auxpass" in [relation for (child, relation) in conj.get_children_with_rels()]:
            subj_rel += "pass"
        
        subj.add_edge(subj_rel, conj)


def xcomp_propagation_per_type(sentence, restriction, is_extra=False):
    outer_restriction = Restriction(nested=[
        [restriction, Restriction(name="new_subj", gov=".?obj")],
        [restriction, Restriction(name="new_subj", gov="nsubj.*")]
    ])
    
    ret = match(sentence.values(), [[outer_restriction]])
    if not ret:
        return
    
    for name_space in ret:
        new_subj, _, _ = name_space['new_subj']
        dep, _, _ = name_space['dep']
        rel = add_eud_info("nsubj", "xsubj")
        new_subj.add_edge(rel if not is_extra else add_extra_info(rel, "xcomp_no_to"), dep)


# Add extra nsubj dependencies when collapsing basic dependencies.
# Some notes copied from SC:
# 1. In the general case, we look for an aux modifier under an xcomp
#   modifier, and assuming there aren't already associated nsubj
#   dependencies as daughters of the original xcomp dependency, we
#   add nsubj dependencies for each nsubj daughter of the governor.
# 2. There is also a special case for "to" words, in which case we add
#   a dependency if and only if there is no nsubj associated with the
#   xcomp AND there is no other aux dependency. This accounts for
#   sentences such as "he decided not to." with no following verb.
# 3. In general, we find that the objects of the verb are better
#   for extra nsubj than the original nsubj of the verb.  For example,
#   "Many investors wrote asking the SEC to require ..."
#   There is no nsubj of asking, but the dobj, SEC, is the extra nsubj of require.
#   Similarly, "The law tells them when to do so"
#   Instead of nsubj(do, law) we want nsubj(do, them)
def xcomp_propagation(sentence):
    to_xcomp_rest = Restriction(name="dep", gov="xcomp", no_sons_of="^(nsubj.*|aux|mark)$", form="^(?i:to)$")
    basic_xcomp_rest = Restriction(name="dep", gov="xcomp", no_sons_of="nsubj.*", form="(?!(^(?i:to)$)).", nested=[[
        Restriction(gov="^(aux|mark)$", form="(^(?i:to)$)")
    ]])

    for xcomp_restriction in [to_xcomp_rest, basic_xcomp_rest]:
        xcomp_propagation_per_type(sentence, xcomp_restriction)


def xcomp_propagation_no_to(sentence):
    xcomp_no_to_rest = Restriction(name="dep", gov="xcomp", no_sons_of="^(aux|mark|nsubj.*)$", form="(?!(^(?i:to)$)).")
    
    xcomp_propagation_per_type(sentence, xcomp_no_to_rest, True)


def advcl_propagation_per_type(sentence, restriction, iids):
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        if 'new_subj' in name_space:
            new_subj_str = 'new_subj'
            cur_iid = None
        else:
            father, _, _ = name_space["father"]
            if father not in iids:
                iids[father] = 0 if len(iids.values()) == 0 else (max(iids.values()) + 1)
            cur_iid = iids[father]
            new_subj_str = 'new_subj_opt'
        
        new_subj, _, _ = name_space[new_subj_str]
        dep, _, _ = name_space['dep']
        new_subj.add_edge(add_extra_info("nsubj", "advcl", iid=cur_iid), dep)


def advcl_propagation(sentence):
    advcl_to_rest = Restriction(nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of="nsubj.*", nested=[[
            Restriction(gov="^(aux|mark)$", form="(^(?i:to)$)")
        ]]),
        Restriction(name="new_subj", gov=".?obj")
    ]])
    
    basic_advcl_rest = Restriction(no_sons_of=".?obj", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of="nsubj.*", nested=[[
            Restriction(gov="^(aux|mark)$", form="(?!(^(?i:as|so|when|if)$)).")
        ]]),
        Restriction(name="new_subj", gov="nsubj.*")
    ]])
    basic_advcl_rest_no_mark = Restriction(no_sons_of=".?obj", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of="(nsubj.*|aux|mark)"),
        Restriction(name="new_subj", gov="nsubj.*")
    ]])
    ambiguous_advcl_rest = Restriction(name="father", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of="nsubj.*", nested=[[
            Restriction(gov="^(aux|mark)$", form="(?!(^(?i:as|so|when|if)$)).")
        ]]),
        Restriction(name="new_subj_opt", gov="(.?obj|nsubj.*)")
    ]])
    ambiguous_advcl_rest_no_mark = Restriction(name="father", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of="(nsubj.*|aux|mark)"),
        Restriction(name="new_subj_opt", gov="(.?obj|nsubj.*)")
    ]])

    iids = dict()
    for advcl_restriction in [advcl_to_rest, basic_advcl_rest, basic_advcl_rest_no_mark, ambiguous_advcl_rest, ambiguous_advcl_rest_no_mark]:
        advcl_propagation_per_type(sentence, advcl_restriction, iids)

def amod_propagation(sentence):
    amod_rest = Restriction(name="father", nested=[[
        Restriction(name="amod", gov="(.*amod.*)", no_sons_of="nsubj.*")
    ]])

    ret = match(sentence.values(), [[amod_rest]])
    if not ret:
        return
    
    for name_space in ret:
        father, _, _ = name_space['father']
        amod, _, _ = name_space['amod']
        father.add_edge(add_extra_info("nsubj", "amod"), amod)


def acl_propagation(sentence):
    acl_rest = Restriction(name="father", nested=[[
        Restriction(name="acl", gov="acl(?!:relcl)", no_sons_of="nsubj.*")
    ]])
    
    ret = match(sentence.values(), [[acl_rest]])
    if not ret:
        return
    
    for name_space in ret:
        father, _, _ = name_space['father']
        acl, _, _ = name_space['acl']
        father.add_edge(add_extra_info("nsubj", "acl"), acl)


# def acl_propagation(sentence):
#     # The apple chosen by me. {nsubj(chosen, apple)}
#     # The apple chosen by god, was eaten by me. {nsubj(chosen, apple)}
#     # I ate the apple chosen by god. {nsubj(chosen, apple), nsubj(chosen, I)}
#     # I ate from the apple chosen by god. {nsubj(chosen, apple), nsubj(chosen, I)}
#     # From the apple chosen by god, I have tried. {nsubj(chosen, apple), nsubj(chosen, I)}
#     # I ate a slice of the apple chosen by god. {nsubj(chosen, apple), nsubj(chosen, I)}
#     # A slice of the apple chosen by god, was eaten by me. {nsubj(chosen, apple)}
#     basic_rest = Restriction(name="father", nested=[[
#         Restriction(name="dep", gov="acl(?!:relcl)", no_sons_of="nsubj.*")
#     ]])
#     subj_rest = Restriction(name="subj", gov=".?subj.*", diff="father")
#     acl_rest = Restriction(name="root_or_predicate", nested=[
#         [basic_rest, subj_rest],
#         [basic_rest]
#     ])
#
#     ret = match(sentence.values(), [[acl_rest]])
#     if not ret:
#         return
#     marked = []
#     iid = 0
#     for name_space in ret:
#         cur_iid = iid
#         father, _, _ = name_space['father']
#         dep, _, _ = name_space['dep']
#         root_or_predicate, _, _ = name_space['root_or_predicate']
#         rp_heads = root_or_predicate.get_parents()
#         subjs = []
#
#         # find subjects that are siblings of the acl's head, and of its parent(s).
#         for rp_head in rp_heads:
#             subjs += [child for (child, rel) in rp_head.get_children_with_rels() if (re.match(".subj.*", rel) and (child not in [father, root_or_predicate]))]
#         if 'subj' in name_space:
#             subj, _, _ = name_space['subj']
#             subjs += [subj]
#
#         candidates = set(subjs + [father])
#         if candidates in marked:
#             continue
#
#         # if no subject found, we have no competition on the new subject title.
#         if not subjs:
#             cur_iid = None
#         else:
#             iid += 1
#
#         # add subj relation from the verb of the acl relation to the found subjects,
#         # and to the head of that relation as well.
#         for subj in subjs:
#             subj.add_edge(add_extra_info("nsubj", "acl", iid=cur_iid), dep)
#         father.add_edge(add_extra_info("nsubj", "acl", iid=cur_iid), dep)
#         marked.append(candidates)


def dep_propagation(sentence):
    dep_rest = Restriction(name="father", nested=[[
        Restriction(name="dep", gov="dep", no_sons_of="nsubj.*"),
        Restriction(name="new_subj_opt", gov="(.?obj|nsubj.*)")
    ]])

    ret = match(sentence.values(), [[dep_rest]])
    if not ret:
        return
    
    iid = 0
    iids = dict()
    for name_space in ret:
        new_subj_opt, _, _ = name_space['new_subj_opt']
        dep, _, _ = name_space['dep']
        father, _, _ = name_space['father']
        if father not in iids:
            iids[father] = iid
            iid += 1
        new_subj_opt.add_edge(add_extra_info("nsubj", "dep", iid=iids[father], uncertain=True), dep)


# TODO - unify with other nmods props
def subj_obj_nmod_propagation_of_nmods_per_type(sentence, rest):
    ret = match(sentence.values(), [[rest]])
    if not ret:
        return
    
    for name_space in ret:
        nmod, _, nmod_rel = name_space['nmod']
        receiver, _, _ = name_space['receiver']
        mediator_rel = name_space['mediator'][2]
        
        nmod.add_edge(add_extra_info(mediator_rel, "like-such-as"), receiver)


def subj_obj_nmod_propagation_of_nmods(sentence):
    obj_rest = Restriction(name="receiver", nested=[[
        Restriction(name="mediator", gov="dobj", nested=[[
            Restriction(name="nmod", gov="nmod:(such_as|like)")
        ]])
    ]])
    
    subj_rest = Restriction(name="receiver", nested=[[
        Restriction(name="mediator", gov=".subj.*", nested=[[
            Restriction(name="nmod", gov="nmod:(such_as|like)")
        ]])
    ]])
    
    nmod_rest = Restriction(name="receiver", nested=[[
        Restriction(name="mediator", gov="nmod", nested=[[
            Restriction(name="nmod", gov="nmod:(such_as|like)")
        ]])
    ]])
    
    for mediator_restriction in [obj_rest, subj_rest, nmod_rest]:
        subj_obj_nmod_propagation_of_nmods_per_type(sentence, mediator_restriction)


def conj_propagation_of_nmods_per_type(sentence, rest, dont_check_precedence=False):
    ret = match(sentence.values(), [[rest]])
    if not ret:
        return
    
    for name_space in ret:
        nmod, _, nmod_rel = name_space['nmod']
        receiver, _, _ = name_space['receiver']
        
        if '.' not in str(receiver.get_conllu_field("id")) and \
                (dont_check_precedence or nmod.get_conllu_field("id") > receiver.get_conllu_field("id")):
            nmod.add_edge(add_extra_info(nmod_rel, "conj", uncertain=True), receiver)


def conj_propagation_of_nmods(sentence):
    son_rest = Restriction(name="receiver", no_sons_of="nmod", nested=[[
        Restriction(gov="conj", nested=[[
            Restriction(name="nmod", gov="nmod(?!(:.*extra|:poss.*))")
        ]])
    ]])

    father_rest = Restriction(nested=[[
        Restriction(name="receiver", gov="conj"),  # TODO: validate no_sons_of="nmod" isn't needed.
        Restriction(name="nmod", gov="nmod(?!:.*extra)")
    ]])
    
    for conj_restriction in [son_rest, father_rest]:
        conj_propagation_of_nmods_per_type(sentence, conj_restriction)


def conj_propagation_of_poss(sentence):
    poss_rest = Restriction(nested=[[
        Restriction(name="receiver", no_sons_of="nmod:poss.*", gov="conj"),
        Restriction(name="nmod", gov="nmod(?!:.*extra)")
    ]])
    
    conj_propagation_of_nmods_per_type(sentence, poss_rest, True)


# phenomena: indexicals
def advmod_propagation(sentence):
    advmod_rest = Restriction(name="gov", nested=[[
        Restriction(name="middle_man", gov="(.?obj|nsubj.*|nmod.*)", nested=[[
            Restriction(name="advmod", gov="advmod", form=advmod_list)
        ]])
    ]])
    ret = match(sentence.values(), [[advmod_rest]])
    if not ret:
        return
    
    for name_space in ret:
        advmod, _, advmod_rel = name_space['advmod']
        _, _, middle_man_rel = name_space['middle_man']
        gov, _, _ = name_space['gov']
        
        if gov not in advmod.get_parents():
            advmod.add_edge(add_extra_info(advmod_rel, "indexical"), gov)


# "I went back to prison"
def nmod_advmod_reconstruction(sentence):
    # the reason for the form restriction: we dont want to catch "all in all"
    nmod_advmod_rest = Restriction(name="gov", nested=[[
        Restriction(name="advmod", gov="advmod", form= "(?!(^(?i:all)$))", nested=[[
            Restriction(name="nmod", gov="nmod", nested=[[
                Restriction(name="case", gov="case")
            ]])
        ]])
    ]])
    ret = match(sentence.values(), [[nmod_advmod_rest]])
    if not ret:
        return
    
    for name_space in ret:
        advmod, _, advmod_rel = name_space['advmod']
        nmod, _, nmod_rel = name_space['nmod']
        case, _, case_rel = name_space['case']
        gov, _, _ = name_space['gov']
        
        if ("as", "advmod") in [(child.get_conllu_field("form").lower(), rel) for child, rel in advmod.get_children_with_rels()]:
            continue
        
        if gov in nmod.get_parents():
            continue
        
        mwe = advmod.get_conllu_field("form").lower() + "_" + case.get_conllu_field("form").lower()
        advmod.replace_edge(advmod_rel, add_extra_info(case_rel, "auto-mwe"), gov, nmod)
        if mwe in nmod_advmod_complex:
            nmod.replace_edge(nmod_rel, add_extra_info(nmod_rel, "auto-mwe"), advmod, gov)
        else:
            case.replace_edge(case_rel, add_extra_info("mwe", "auto-mwe"), nmod, advmod)
            nmod.replace_edge(nmod_rel, add_extra_info(add_eud_info(nmod_rel, mwe), "auto-mwe"), advmod, gov)


def appos_propagation(sentence):
    appos_rest = Restriction(name="gov", nested=[[
        Restriction(name="appos", gov="appos")
    ]])
    ret = match(sentence.values(), [[appos_rest]])
    if not ret:
        return
    
    for name_space in ret:
        appos, _, _ = name_space['appos']
        gov, _, _ = name_space['gov']
        
        for (gov_head, gov_rel) in gov.get_new_relations():
            if (gov_head, gov_rel) not in appos.get_new_relations():
                appos.add_edge(add_extra_info(gov_rel, "appos"), gov_head)


# find the closest cc to the conj with precedence for left hand ccs
def attach_best_cc(conj, ccs, noun, verb):
    closest_cc = None
    closest_dist = None
    for cur_cc in ccs:
        cur_dist = conj.dist(cur_cc)
        if (not closest_cc) or \
                ((copysign(1, closest_dist) == copysign(1, cur_dist)) and (abs(cur_dist) < abs(closest_dist))) or \
                ((copysign(1, closest_dist) != copysign(1, cur_dist)) and (copysign(1, cur_dist) == -1)):
            closest_cc = cur_cc
            closest_dist = conj.dist(closest_cc)
    if closest_cc:
        closest_cc.replace_edge("cc", add_extra_info("cc", "copula"), noun, verb)


def copula_reconstruction(sentence):
    cop_rest = Restriction(name="father", nested=[[
        Restriction(name="old_root", xpos="(?!:(VB.?|BES|HVS))", nested=[[
            Restriction(name="cop", gov="cop"),
        ]])
    ]])
    ret = match(sentence.values(), [[cop_rest]])
    if not ret:
        return

    for name_space in ret:
        old_root, _, _ = name_space['old_root']
        cop, _, _ = name_space['cop']
        
        new_id = cop.get_conllu_field('id') + 0.1
        new_root = cop.copy(
            new_id=new_id,
            form="_",
            lemma="_",
            upos="_",
            xpos="_",
            feats="_",
            head="_",
            deprel="_",
            deps=None)
        
        # transfer old-root's outgoing relation to new-root
        for head, rel in old_root.get_new_relations():
            old_root.remove_edge(rel, head)
            new_root.add_edge(add_extra_info(rel, "copula"), head)

        # transfer all old-root's children that are to be transferred
        ccs = [cc_child for cc_child, cc_rel in old_root.get_children_with_rels() if cc_rel == "cc"]
        subjs = []
        new_out_rel = "xcomp"
        for child, rel in old_root.get_children_with_rels():
            if re.match("(aux.*|discourse|mark|punct|advcl|xcomp|ccomp|advmod|expl|parataxis)", rel):
                child.replace_edge(rel, add_extra_info(rel, "copula"), old_root, new_root)
            elif re.match("(.subj.*)", rel):
                child.replace_edge(rel, add_extra_info(rel, "copula"), old_root, new_root)
                subjs.append(child)
            elif re.match("(case)", rel):
                new_out_rel = "nmod"
            elif "cop" == rel:
                child.replace_edge(rel, add_extra_info("aux", "copula"), old_root, new_root)
            elif ("conj" == rel) and (re.match("(VB.?|BES|HVS|JJ.?)", child.get_conllu_field("xpos"))):
                child.replace_edge(rel, add_extra_info(rel, "copula"), old_root, new_root)
                attach_best_cc(child, ccs, old_root, new_root)
            # else: {'compound', 'nmod', 'acl:relcl', 'amod', 'det', 'nmod:poss', 'nummod', 'nmod:tmod', some: 'cc', 'conj'}
        
        # update old-root's outgoing relation
        if re.match("JJ.?", old_root.get_conllu_field("xpos")):
            for subj in subjs:
                old_root.add_edge(add_extra_info("amod", "copula"), subj)
            new_root.set_conllu_field("form", "QUALITY")
        else:
            new_root.set_conllu_field("form", "STATE")
        
        old_root.add_edge(add_extra_info(new_out_rel, "copula"), new_root)
        
        sentence[new_id] = new_root


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
    [child.replace_edge(child_rel, child_rel, old_head, new_head) for (child, child_rel) in old_head.get_children_with_rels()]


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
    
    restriction = Restriction(nested=[[
        Restriction(gov="(case|advmod)", no_sons_of=".*", name="w1", form="^" + forms[0] + "$"),
        Restriction(gov="case", no_sons_of=".*", follows="w1", name="w2", form="^" + forms[1] + "$")
    ]])
    ret = match(sentence.values(), [[restriction]])
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
    restriction = Restriction(name="gov", nested=[[
        Restriction(name="w1", followed_by="w2", form="^" + forms[0] + "$", nested=[
            [inner_rest, Restriction(name="cop", gov="cop")],  # TODO: after adding the copula reconstuction, maybe this would be redundant
            [inner_rest]
        ])
    ]])
    
    ret = match(sentence.values(), [[restriction]])
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
        if (w1_rel.lower() == "root") or (cop and (w1_rel in clause_relations)):
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
    
    restriction = Restriction(name="gov", nested=[[
        Restriction(name="w2", followed_by="w3", follows="w1", form="^" + forms[1] + "$", nested=[[
            Restriction(name="gov2", gov="(nmod|acl|advcl)", nested=[[
                Restriction(name="w3", gov="(case|mark)", no_sons_of=".*", form="^" + forms[2] + "$")
            ]]),
            Restriction(name="w1", gov="^(case)$", no_sons_of=".*", form="^" + forms[0] + "$")
        ]])
    ]])
    
    ret = match(sentence.values(), [[restriction]])
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
def demote_per_type(sentence, restriction):
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        old_gov, old_gov_head, old_gov_rel = name_space['w1']
        w2, w2_head, w2_rel = name_space['w2']
        gov2, gov2_head, gov2_rel = name_space['gov2']
        
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
        
        [child.replace_edge(rel, rel, old_gov, gov2) for (child, rel) in old_gov.get_children_with_rels() if rel == "case"]
        gov2.replace_edge(gov2_rel, old_gov_rel, old_gov, old_gov_head)
        create_mwe(words, gov2, add_eud_info("det", "qmod"))
        # TODO: consider bringing back the 'if statement': [... if rel in ["punct", "acl", "acl:relcl", "amod"]]
        [child.replace_edge(rel, rel, gov2_head, gov2) for (child, rel) in gov2_head.get_children_with_rels()]


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
        Restriction(name="w1", form=quant_mod_2w_det, followed_by="w2", nested=[[
            Restriction(name="gov2", gov="nmod", xpos="(NN.*)", nested=[[
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


def assign_refs(ret):
    ref_assignments = dict()
    descendents = dict()
    for name_space in ret:
        for level in ['child_ref', 'grand_ref']:
            if level in name_space:
                mods_descendent = (name_space[level][0].get_conllu_field('id'), name_space[level])
                if name_space['mod'] in descendents:
                    descendents[name_space['mod']].append(mods_descendent)
                else:
                    descendents[name_space['mod']] = [mods_descendent]
    
    for mod, mods_descendents in descendents.items():
        leftmost_descendent = sorted(mods_descendents)[0]
        ref_assignments[mod] = leftmost_descendent[1]
    
    return ref_assignments


# Look for ref rules for a given word. We look through the
# children and grandchildren of the acl:relcl dependency, and if any
# children or grandchildren is a that/what/which/etc word,
# we take the leftmost that/what/which/etc word as the dependent
# for the ref TypedDependency.
# Then we collapse the referent relation such as follows. e.g.:
# "The man that I love ... " dobj(love, that) -> ref(man, that) dobj(love, man)
def add_ref_and_collapse(sentence, enhanced_plus_plus, enhanced_extra):
    child_rest = Restriction(name="child_ref", form=relativizing_word_regex)
    grandchild_rest = Restriction(nested=[[
        Restriction(name="grand_ref", form=relativizing_word_regex)
    ]])
    restriction = Restriction(name="gov", nested=[[
        Restriction(name="mod", gov='acl:relcl', nested=[
            [grandchild_rest, child_rest],
            [grandchild_rest],
            [child_rest],
            []
        ]),
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    ref_assignments = assign_refs(ret)

    for name_space in ret:
        gov, gov_head, gov_rel = name_space['gov']
        if ref_assignments and name_space['mod'] in ref_assignments:
            if not enhanced_plus_plus:
                continue
            leftmost, leftmost_head, leftmost_rel = ref_assignments[name_space['mod']]
            if gov not in leftmost.get_parents():
                leftmost.replace_edge(leftmost_rel, "ref", leftmost_head, gov)
                [child.replace_edge(rel, rel, leftmost, gov) for child, rel in leftmost.get_children_with_rels()]
                gov.add_edge(leftmost_rel, leftmost_head, extra_info=EXTRA_INFO_STUB)
        # this is for reduce-relative-clause
        elif enhanced_extra:
            leftmost_head, _, _ = name_space['mod']
            rels_with_pos = {(relation, child.get_conllu_field('xpos')): child.get_conllu_field('form') for (child, relation) in leftmost_head.get_children_with_rels()}
            rels_only = [rel for (rel, pos) in rels_with_pos.keys()]

            if ("nsubj" not in rels_only) and ("nsubjpass" not in rels_only):
                leftmost_rel = 'nsubj'
            
            # some relativizers that were simply missing on the eUD.
            elif 'where' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = 'nmod'
            elif 'how' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = 'nmod'
            elif 'when' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = 'nmod:tmod'
            elif 'why' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = add_eud_info('nmod', 'because_of')
            
            # continue with *reduced* relcl, cased of orphan case/marker should become nmod and not obj
            elif ('nmod', 'RB') in rels_with_pos:
                leftmost_rel = add_eud_info('nmod', rels_with_pos[('nmod', 'RB')])
            elif ('advmod', 'RB') in rels_with_pos:
                leftmost_rel = add_eud_info('nmod', rels_with_pos[('advmod', 'RB')])
            elif ('nmod', 'IN') in rels_with_pos:
                leftmost_rel = add_eud_info('nmod', rels_with_pos[('nmod', 'IN')])
            
            # this is a special case in which its not the head of the relative clause who get the nmod connection but one of its objects,
            # as sometimes the relcl modifies the should-have-been-inner-object's-modifier
            # TODO: add an example, this is very unclear
            elif 'dobj' in rels_only:
                objs = [child for child, rel in leftmost_head.get_children_with_rels() if rel == 'dobj']
                for obj in objs:
                    rels_with_pos_obj = {(relation, child.get_conllu_field('xpos')): child for
                                     (child, relation) in obj.get_children_with_rels()}
                    if (('nmod', 'IN') in rels_with_pos_obj) or (('nmod', 'RB') in rels_with_pos_obj):
                        case = rels_with_pos_obj[('nmod', 'IN')] if ('nmod', 'IN') in rels_with_pos_obj else rels_with_pos_obj[('nmod', 'RB')]
                        gov.add_edge(add_extra_info(add_eud_info("nmod", case.get_conllu_field('form')), "reduced-relcl"), obj, extra_info=EXTRA_INFO_STUB)
                        case.add_edge(add_extra_info("case", "reduced-relcl"), gov)
                        return
                # this means we didn't found so rel should be dobj, but we didn't reach the last else because  we had some other objects.
                leftmost_rel = 'dobj'
            else:
                leftmost_rel = 'dobj'
            gov.add_edge(add_extra_info(leftmost_rel, "reduced-relcl"), leftmost_head, extra_info=EXTRA_INFO_STUB)


# resolves the following multi word conj phrases:
#   a. 'but(cc) not', 'if not', 'instead of', 'rather than', 'but(cc) rather'. GO TO negcc
#   b. 'as(cc) well as', 'but(cc) also', 'not to mention', '&'. GO TO and
# NOTE: This is bad practice (and sometimes not successful neither for SC or for us) for the following reasons:
#   1. Not all parsers mark the same words as cc (if at all), so looking for the cc on a specific word is wrong.
#       as of this reason, for now we and SC both miss: if-not, not-to-mention
#   2. Some of the multi-words are already treated as multi-word prepositions (and are henceforth missed):
#       as of this reason, for now we and SC both miss: instead-of, rather-than
def get_assignment(sentence, cc):
    cc_cur_id = cc.get_conllu_field('id')
    prev_forms = "_".join([info.get_conllu_field('form') for (iid, info) in sentence.items()
                           if iid != 0 and (cc_cur_id - 1 == iid or cc_cur_id == iid)])
    next_forms = "_".join([info.get_conllu_field('form') for (iid, info) in sentence.items()
                           if cc_cur_id + 1 == iid or cc_cur_id == iid])
    if next_forms in neg_conjp_next or prev_forms in neg_conjp_prev:
        return "negcc"
    elif (next_forms in and_conjp_next) or (cc.get_conllu_field('form') == '&'):
        return "and"
    else:
        return cc.get_conllu_field('form')


# In case multiple coordination marker depend on the same governor
# the one that precedes the conjunct is appended to the conjunction relation or the
# first one if no preceding marker exists.
def assign_ccs_to_conjs(sentence, ret):
    cc_assignments = dict()
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
            cc_assignments[((cc_or_conj, head, rel), cur_cc)] = get_assignment(sentence, cur_cc[0])
    return cc_assignments


# Adds the type of conjunction to all conjunct relations
# Some multi-word coordination markers are collapsed to conj:and or conj:negcc
def conj_info(sentence):
    restriction = Restriction(name="gov", nested=[[
        Restriction(name="cc", gov="^(cc)$"),
        Restriction(name="conj", gov="^(conj)$")
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    # assign ccs to conjs according to precedence
    cc_assignments = assign_ccs_to_conjs(sentence, ret)
    
    for name_space in ret:
        gov, _, _ = name_space['gov']
        cc, _, cc_rel = name_space['cc']
        conj, _, conj_rel = name_space['conj']

        if ((conj, gov, conj_rel), (cc, gov, cc_rel)) not in cc_assignments:
            continue
        cc_assignment = cc_assignments[((conj, gov, conj_rel), (cc, gov, cc_rel))]
        
        conj.replace_edge(conj_rel, add_eud_info(conj_rel, cc_assignment), gov, gov)


# The label of the conjunct relation includes the conjunction type
# because if the verb has multiple cc relations then it can be impossible
# to infer which coordination marker belongs to which conjuncts.
def expand_per_type(sentence, restriction, is_pp):
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    # assign ccs to conjs according to precedence
    cc_assignments = assign_ccs_to_conjs(sentence, ret)
    
    nodes_copied = 0
    last_copy_id = -1
    for name_space in ret:
        gov, _, gov_rel = name_space['gov']
        to_copy, _, _ = name_space['to_copy']
        cc, cc_head, cc_rel = name_space['cc']
        conj, conj_head, conj_rel = name_space['conj']
        
        if ((conj, conj_head, conj_rel), (cc, cc_head, cc_rel)) not in cc_assignments:
            continue
        cc_assignment = cc_assignments[((conj, gov, conj_rel), (cc, gov, cc_rel))]
        
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
        copy_node.add_edge(add_eud_info("conj", cc_assignment), to_copy)
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
            modifier.add_edge(add_eud_info(modifier_rel, conj.get_conllu_field('form')), copy_node)


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
            Restriction(name="cc", gov="^(cc)$"),
            Restriction(name="conj", gov="conj", nested=[[
                Restriction(gov="case")
            ]])
        ]])
    ]])
    
    prep_restriction = Restriction(name="to_copy", nested=[[
        Restriction(name="modifier", nested=[[
            Restriction(name="gov", gov="case", nested=[[
                Restriction(name="cc", gov="^(cc)$"),
                Restriction(name="conj", gov="conj")
            ]])
        ]])
    ]])
    
    for rl, is_pp in [(pp_restriction, True), (prep_restriction, False)]:
        expand_per_type(sentence, rl, is_pp)


# TODO: remove when moving to UD-version2
def fix_nmod_npmod(sentence):
    restriction = Restriction(nested=[[
        Restriction(name="npmod", gov="^nmod:npmod$")
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        npmod, npmod_head, npmod_rel = name_space['npmod']
        npmod.replace_edge(npmod_rel, "compound", npmod_head, npmod_head)


def hyphen_reconstruction(sentence):
    restriction = Restriction(name="subj", nested=[[
        Restriction(name="verb", gov="^(amod)$", xpos="VB.", nested=[[
            Restriction(name="hyphen", form="-", gov="^(punct)$", xpos="HYPH"),
            Restriction(name="noun", gov="^(compound)$", xpos="NN.?")
        ]]),
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        subj, _, _ = name_space['subj']
        verb, _, _ = name_space['verb']
        noun, _, _ = name_space['noun']
        
        subj.add_edge(add_extra_info("nsubj", "hyph"), verb)
        noun.add_edge(add_extra_info("nmod", "hyph"), verb)


# The bottle was broken by me.
def passive_alteration(sentence):
    restriction = Restriction(name="predicate", nested=[
        [
            Restriction(name="subjpass", gov=".subjpass"),
            Restriction(name="agent", gov="nmod:agent")
        ],
        [Restriction(name="subjpass", gov=".subjpass")]
    ])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        subj, _, subj_rel = name_space['subjpass']
        predicate, _, _ = name_space['predicate']
        if 'agent' in name_space:
            agent, _, _ = name_space['agent']
            agent.add_edge(add_extra_info("nsubj", "passive"), predicate)
        
        # the special case of csubj (divided into ccomp and xcomp according to 'that' and 'to' subordinates.
        subj_new_rel = "dobj"
        if subj_rel.startswith("csubj"):
            for child, rel in subj.get_children_with_rels():
                if (rel == "mark") and (child.get_conllu_field("form") == "to"):
                    subj_new_rel = "xcomp"
                elif ("obj" in rel) and (child.get_conllu_field("form") == "that") and (child.get_conllu_field("xpos") == "IN"):
                    subj_new_rel = "ccomp"
        elif "dobj" in [rel for (_, rel) in predicate.get_children_with_rels()]:
            subj_new_rel = "iobj"
        
        subj.add_edge(add_extra_info(subj_new_rel, "passive"), predicate)
    

def convert_sentence(sentence, enhanced, enhanced_plus_plus, enhanced_extra, remove_node_adding_conversions):
    # correctDependencies - correctSubjPass, processNames and removeExactDuplicates.
    # the last two have been skipped. processNames for future treatment, removeExactDuplicates for redundancy.
    correct_subj_pass(sentence)
    
    if enhanced_extra:
        if not remove_node_adding_conversions:
            copula_reconstruction(sentence)
        fix_nmod_npmod(sentence)
        hyphen_reconstruction(sentence)
    
    if enhanced_plus_plus:
        # processMultiwordPreps: processSimple2WP, processComplex2WP, process3WP
        process_simple_2wp(sentence)
        process_complex_2wp(sentence)
        process_3wp(sentence)
        # demoteQuantificationalModifiers
        demote_quantificational_modifiers(sentence)
        # add copy nodes: expandPPConjunctions, expandPrepConjunctions
        if not remove_node_adding_conversions:
            expand_pp_or_prep_conjunctions(sentence)

    if enhanced_extra:
        nmod_advmod_reconstruction(sentence)

    if enhanced:
        # addCaseMarkerInformation
        if not g_remove_enhanced_extra_info:
            passive_agent(sentence)
        prep_patterns(sentence, '^nmod$', 'case')
        prep_patterns(sentence, '^(advcl|acl)$', '^(mark|case)$')
        
        if not g_remove_enhanced_extra_info:
            # addConjInformation
            conj_info(sentence)
    
    # referent: addRef, collapseReferent
    if enhanced_plus_plus or enhanced_extra:
        add_ref_and_collapse(sentence, enhanced_plus_plus, enhanced_extra)

    if enhanced:
        # treatCC
        heads_of_conjuncts(sentence)
        subj_of_conjoined_verbs(sentence)
        
        # addExtraNSubj
        xcomp_propagation(sentence)
    
    if enhanced_extra:
        xcomp_propagation_no_to(sentence)
        advcl_propagation(sentence)
        acl_propagation(sentence)
        amod_propagation(sentence)
        dep_propagation(sentence)
        conj_propagation_of_nmods(sentence)
        conj_propagation_of_poss(sentence)
        advmod_propagation(sentence)
        appos_propagation(sentence)
        subj_obj_nmod_propagation_of_nmods(sentence)
        passive_alteration(sentence)
    
    # correctSubjPass
    correct_subj_pass(sentence)
    
    return sentence


def convert(parsed, enhanced, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_enhanced_extra_info, remove_aryeh_extra_info, remove_node_adding_conversions):
    global g_remove_enhanced_extra_info, g_remove_aryeh_extra_info
    g_remove_enhanced_extra_info = remove_enhanced_extra_info
    g_remove_aryeh_extra_info = remove_aryeh_extra_info
    
    last_converted_sentences = []
    converted_sentences = parsed
    i = 0
    
    # we iterate till convergence or till user defined maximum is reached - the first to come.
    while (i < conv_iterations) and (set([(head.get_conllu_field("form"), rel) for sent in converted_sentences for tok in sent.values() for (head, rel) in tok.get_new_relations()]) != last_converted_sentences):
        last_converted_sentences = set([(head.get_conllu_field("form"), rel) for sent in converted_sentences for tok in sent.values() for (head, rel) in tok.get_new_relations()])
        temp = []
        for sentence in converted_sentences:
            temp.append(convert_sentence(sentence, enhanced, enhanced_plus_plus, enhanced_extra, remove_node_adding_conversions))
        converted_sentences = temp
        i += 1
    
    if set([(head.get_conllu_field("form"), rel) for sent in converted_sentences for tok in sent.values() for (head, rel) in tok.get_new_relations()]) == last_converted_sentences:
        i -= 1
    
    return converted_sentences, i


