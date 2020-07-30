# conversions as been done by StanfordConverter (a.k.a SC) version TODO
# global nuances from their converter:
#   1. we always write to 'deps' (so at first we copy 'head'+'deprel' to 'deps'), while they sometimes write back to 'deprel'.
#   2. we think like a multi-graph, so we operate on every relation/edge between two nodes, while they on first one found.
#   3. we look for all fathers as we can have multiple fathers, while in SC they look at first one found.

import sys
import re
from math import copysign
import inspect
from typing import List, Dict, Tuple
from enum import Enum
from abc import ABC, abstractmethod

from .matcher import match, Restriction
from .graph_token import Token

# ********************************************* Constants&Globals *********************************************


EXTRA_INFO_STUB = 1
g_remove_enhanced_extra_info = False
g_remove_bart_extra_info = False
g_remove_node_adding_conversions = False
g_ud_version = 1  # default UD version we work with is 1

# language specific lists
nmod_advmod_complex = ["back_to", "back_in", "back_at", "early_in", "late_in", "earlier_in"]
two_word_preps_regular = ["across_from", "along_with", "alongside_of", "apart_from", "as_for", "as_from", "as_of", "as_per", "as_to", "aside_from", "based_on", "close_by", "close_to", "contrary_to", "compared_to", "compared_with", " depending_on", "except_for", "exclusive_of", "far_from", "followed_by", "inside_of", "irrespective_of", "next_to", "near_to", "off_of", "out_of", "outside_of", "owing_to", "preliminary_to", "preparatory_to", "previous_to", "prior_to", "pursuant_to", "regardless_of", "subsequent_to", "thanks_to", "together_with"]
two_word_preps_complex = ["apart_from", "as_from", "aside_from", "away_from", "close_by", "close_to", "contrary_to", "far_from", "next_to", "near_to", "out_of", "outside_of", "pursuant_to", "regardless_of", "together_with"]
three_word_preps = ["by_means_of", "in_accordance_with", "in_addition_to", "in_case_of", "in_front_of", "in_lieu_of", "in_place_of", "in_spite_of", "on_account_of", "on_behalf_of", "on_top_of", "with_regard_to", "with_respect_to"]
quant_mod_3w = "(?i:lot|assortment|number|couple|bunch|handful|litany|sheaf|slew|dozen|series|variety|multitude|wad|clutch|wave|mountain|array|spate|string|ton|range|plethora|heap|sort|form|kind|type|version|bit|pair|triple|total)"
quant_mod_2w = "(?i:lots|many|several|plenty|tons|dozens|multitudes|mountains|loads|pairs|tens|hundreds|thousands|millions|billions|trillions|[0-9]+s)"
quant_mod_2w_det = "(?i:some|all|both|neither|everyone|nobody|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|billion|trillion|[0-9]+)"
relativizing_word_regex = "(?i:that|what|which|who|whom|whose)"
neg_conjp_prev = ["if_not"]
neg_conjp_next = ["instead_of", "rather_than", "but_rather", "but_not"]
and_conjp_next = ["as_well", "but_also"]
advmod_list = "(here|there|now|later|soon|before|then|today|tomorrow|yesterday|tonight|earlier|early)"
evidential_list = "^(seem|appear|be|sound)$"
aspectual_list = "^(begin|continue|delay|discontinue|finish|postpone|quit|resume|start|complete)$"
reported_list = "^(report|say|declare|announce|tell|state|mention|proclaim|replay|point|inform|explain|clarify|define|expound|describe|illustrate|justify|demonstrate|interpret|elucidate|reveal|confess|admit|accept|affirm|swear|agree|recognise|testify|assert|think|claim|allege|argue|assume|feel|guess|imagine|presume|suggest|argue|boast|contest|deny|refute|dispute|defend|warn|maintain|contradict)$"
agent_original_case = "by"

# UDv1 specifics:
clause_relations = ["conj", "xcomp", "ccomp", "acl", "advcl", "acl:relcl", "parataxis", "appos", "list"]


class ConvTypes(Enum):
    EUD = 1
    EUDPP = 2
    BART = 3


class NameSpace(Enum):
    NODE = 0
    HEAD = 1
    REL = 2

# ********************************************* Helper Functions *********************************************


class ConvsCanceler:
    def __init__(self, cancel_list: List[str] = None):
        self.cancel_list = cancel_list
        self.original = {func_name: func_pointer for (func_name, func_pointer) in inspect.getmembers(sys.modules[__name__], inspect.isfunction)
                         if (func_name.startswith("eud") or func_name.startswith("eudpp") or func_name.startswith("extra"))}
        self._func_names = self.original.keys()
    
    def restore_funcs(self):
        # best effort in cleanup
        try:
            for func_name, func_pointer in self.original.items():
                setattr(sys.modules[__name__], func_name, func_pointer)
        except KeyError:
            pass
    
    def override_funcs(self):
        if self.cancel_list:
            for func_name in self.cancel_list:
                if func_name not in self._func_names:
                    raise ValueError(f"{func_name} is not a real function name")
                setattr(sys.modules[__name__], func_name, lambda *x: None)
    
    def update_funcs(self, func_names: List[str]):
        if self.cancel_list:
            self.cancel_list.extend(func_names)
        else:
            self.cancel_list = func_names
    
    def update_funcs_by_prefix(self, prefix: str):
        func_names = list()
        for func_name in self._func_names:
            if func_name.startswith(prefix):
                func_names.append(func_name)
        self.update_funcs(func_names)
    
    @staticmethod
    def get_conversion_names():
        return set(ConvsCanceler()._func_names)


def split_by_at(label):
    # For the rare case which involvs a '@' preposition,
    # we temporarily replace it with 'at', instead of simply doing rel.split("@")
    return [x.replace(":at", ":@") for x in label.replace(":@", ":at").split("@")]


def naked_label(label):
    return split_by_at(label)[0].split(":")[0]


def add_eud_info(orig, extra):
    at = orig.split("@")
    base = at[0]
    if ":" in orig:
        base = at[0].split(":")[0]
    return base + ((":" + extra) if not g_remove_enhanced_extra_info else "") + (("@" + at[1]) if len(at) > 1 else "")


def add_extra_info(orig, dep, dep_type=None, phrase=None, iid=None, uncertain=False, prevs=None):
    global g_remove_bart_extra_info
    
    source_str = ""
    if not g_remove_bart_extra_info:
        iid_str = ""
        if iid is not None:
            iid_str = "#" + str(iid)
        prevs_str = ""
        if (prevs is not None) and (len(prevs.split("@")) > 1):
            prevs_str = "+" + prevs.split("@")[-1]
        dep_args = ", ".join([x for x in [dep_type, phrase, "UNC" if uncertain else None] if x])
        source_str = "@" + dep + "(" + dep_args + ")" + iid_str + prevs_str
    
    return orig + source_str


def udv(udv1_str: str, udv2_str: str) -> str:
    return udv1_str if g_ud_version == 1 else udv2_str


# ********************************************* Conversion Functions *********************************************


# Purpose: This method corrects subjects of verbs for which we identified an auxpass,
#   but didn't identify the subject as passive.
# SC notes:
#   1. original name = correctSubjPass
#   2. We changed the regex of "subj" restriction, to avoid the need
#       to filter .subjpass relations in the graph-rewriting part
class CorrectSubjPass:
    @staticmethod
    def get_conv_type() -> ConvTypes:
        return ConvTypes.EUD

    @staticmethod
    def get_restriction() -> Restriction:
        return Restriction(name="root", after="subj", nested=[[
            Restriction(gov='auxpass', name="aux"),
            Restriction(gov="^(.subj|.subj(?!pass).*)$", name="subj")
        ]])

    @staticmethod
    def rewrite(hit_ns: Dict[str, Tuple[Token, Token, str]], sentence: List[Token] = None) -> None:
        hit_ns['subj'][NameSpace.NODE.value].replace_edge(
            hit_ns['subj'][NameSpace.REL.value],
            re.sub("(?<!x)subj", "subjpass", hit_ns['subj'][NameSpace.REL.value]),
            hit_ns['root'][NameSpace.NODE.value],
            hit_ns['root'][NameSpace.NODE.value])


# Purpose: add 'agent' to modifiers if they are cased by agent_original_case, and have an auxpass sibling
# SC notes:
#   1. original name = addCaseMarkerInformation
class PassiveAgent:
    @staticmethod
    def get_conv_type() -> ConvTypes:
        return ConvTypes.EUD

    @staticmethod
    def get_restriction() -> Restriction:
        return Restriction(name="gov", nested=[[
            Restriction(gov='auxpass'),
            Restriction(name="mod", gov=f"^({udv('nmod', 'obl')})$", nested=[[
                Restriction(gov='case', form=f"^(?i:{agent_original_case})$")
            ]])
        ]])

    @staticmethod
    def rewrite(hit_ns: Dict[str, Tuple[Token, Token, str]], sentence: List[Token] = None) -> None:
        hit_ns['mod'][NameSpace.NODE.value].replace_edge(
            hit_ns['mod'][NameSpace.REL.value],
            add_eud_info(hit_ns['mod'][NameSpace.REL.value], "agent"),
            hit_ns['gov'][NameSpace.NODE.value],
            hit_ns['gov'][NameSpace.NODE.value])


# Purpose: move preposition to the relation label including cases of multi word preposition
# SC notes:
#   1. original name = addCaseMarkerInformation
#   2. In SC they are more harsh with multi words prepositions that are not following,
#       but we simply ignore this rare (or impossible case?), for simplicity
class PrepPatterns:
    @staticmethod
    def get_conv_type() -> ConvTypes:
        return ConvTypes.EUD

    @staticmethod
    def get_restriction() -> Restriction:
        return Restriction(name="gov", nested=[[
            Restriction(name="mod", gov='^(advcl|acl|nmod|obl)$', nested=[
                [
                    Restriction(name="c1", gov='^(mark|case)$', followed_by="c2", nested=[[
                        Restriction(name="c2", gov="mwe"),
                        Restriction(name="c3", gov="mwe", diff="c2", follows="c2")
                    ]])
                ], [
                    Restriction(name="c1", gov='^(mark|case)$', followed_by="c2", nested=[[
                        Restriction(name="c2", gov="mwe")
                    ]])
                ], [
                    # here we want to find any one word that marks a modifier,
                    # except for cases in which agent_original_case was used for 'agent' identification,
                    # but the 'exact' notation will prevent those from being caught
                    Restriction(name="c1", gov='^(mark|case)$')
                ]
            ])
        ]])

    @staticmethod
    def rewrite(hit_ns: Dict[str, Tuple[Token, Token, str]], sentence: List[Token] = None) -> None:
        # Concatenating the multi-word preposition.
        prep_sequence = "_".join([x[NameSpace.NODE.value].get_conllu_field('form') for x in filter(None, [
            hit_ns.get('c1'), hit_ns.get('c2'), hit_ns.get('c3')])]).lower()
        hit_ns['mod'][NameSpace.NODE.value].replace_edge(
            hit_ns['mod'][NameSpace.REL.value],
            add_eud_info(hit_ns['mod'][NameSpace.REL.value], prep_sequence),
            hit_ns['gov'][NameSpace.NODE.value],
            hit_ns['gov'][NameSpace.NODE.value])


def eud_heads_of_conjuncts(sentence):
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
        if (gov_head, gov_rel) not in gov.get_extra_info_edges() \
                and gov_head != dep \
                and (gov_head, naked_label(gov_rel)) not in [(h, naked_label(r)) for (h, r) in dep.get_new_relations()]:
            dep.add_edge(gov_rel, gov_head)
        
        # NOTE: this is not part of the original SC.
        # if the shared head is an nmod/acl/advcl, then propagate the case/marker also between the conjuncts.
        if \
                (gov_rel.startswith("nmod") and all([not r.startswith("case") for (c, r) in dep.get_children_with_rels()])) or \
                (re.match("acl|advcl", gov_rel) and all([not re.match("case|mark", r) for (c, r) in dep.get_children_with_rels()])):
            for c, r in gov.get_children_with_rels():
                if re.match("case|mark", r):
                    c.add_edge(r, dep)
        
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
def eud_subj_of_conjoined_verbs(sentence):
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
        new_subj, _, rel = name_space['new_subj']
        dep, _, _ = name_space['dep']
        new_subj.add_edge(add_eud_info("nsubj", "xcomp(INF)") if not is_extra else
                          add_extra_info("nsubj", "xcomp", dep_type="GERUND", prevs=rel), dep)


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
def eud_xcomp_propagation(sentence):
    to_xcomp_rest = Restriction(name="dep", gov="xcomp", no_sons_of="^(nsubj.*|aux|mark)$", xpos="^(TO)$")
    basic_xcomp_rest = Restriction(name="dep", gov="xcomp", no_sons_of="nsubj.*", xpos="(?!(^(TO)$)).", nested=[[
        Restriction(gov="^(aux|mark)$", xpos="(^(TO)$)")
    ]])

    for xcomp_restriction in [to_xcomp_rest, basic_xcomp_rest]:
        xcomp_propagation_per_type(sentence, xcomp_restriction)


def extra_xcomp_propagation_no_to(sentence):
    xcomp_no_to_rest = Restriction(name="dep", gov="xcomp", no_sons_of="^(aux|mark|nsubj.*)$", xpos="(VB.?)")
    
    xcomp_propagation_per_type(sentence, xcomp_no_to_rest, True)


def advcl_or_dep_propagation_per_type(sentence, restriction, type_, unc, iids):
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        dep, _, _ = name_space['dep']
        if 'new_subj' in name_space:
            new_subj_str = 'new_subj'
            cur_iid = None
            # in case the father has more than one subject, we dont want to take care now, but later.
            if len([rel for child, rel in name_space['father'][0].get_children_with_rels() if re.match(".subj.*", rel)]) > 1:
                continue
        else:
            if dep not in iids:
                iids[dep] = 0 if len(iids.values()) == 0 else (max(iids.values()) + 1)
            cur_iid = iids[dep]
            new_subj_str = 'new_subj_opt'
        
        new_subj, _, rel = name_space[new_subj_str]
        mark, _, _ = name_space['mark'] if 'mark' in name_space else (None, _, _)
        phrase = mark.get_conllu_field("form") if mark else "NULL"
        new_subj.add_edge(add_extra_info("nsubj", type_, phrase=phrase, prevs=rel, iid=cur_iid, uncertain=unc), dep)


def extra_advcl_propagation(sentence, iids):
    advcl_to_rest = Restriction(name="father", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of=".subj.*", nested=[[
            Restriction(name="mark", gov="^(aux|mark)$", form="(^(?i:to)$)")
        ]]),
        Restriction(name="new_subj", gov=".?obj")
    ]])
    
    basic_advcl_rest = Restriction(name="father", no_sons_of=".?obj", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of=".subj.*", nested=[[
            Restriction(name="mark", gov="^(aux|mark)$", form="(?!(^(?i:as|so|when|if)$)).")
        ]]),
        Restriction(name="new_subj", gov="nsubj.*")
    ]])
    basic_advcl_rest_no_mark = Restriction(name="father", no_sons_of=".?obj", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of="(.subj.*|aux|mark)"),
        Restriction(name="new_subj", gov="nsubj.*")
    ]])
    
    for advcl_restriction in [advcl_to_rest, basic_advcl_rest, basic_advcl_rest_no_mark]:
        advcl_or_dep_propagation_per_type(sentence, advcl_restriction, "advcl", False, iids)


def extra_advcl_ambiguous_propagation(sentence, iids):
    ambiguous_advcl_rest = Restriction(name="father", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of=".subj.*", nested=[[
            Restriction(name="mark", gov="^(aux|mark)$", form="(?!(^(?i:as|so|when|if)$)).")
        ]]),
        Restriction(name="new_subj_opt", gov="(.?obj|nsubj.*)")
    ]])
    ambiguous_advcl_rest_no_mark = Restriction(name="father", nested=[[
        Restriction(name="dep", gov="advcl", no_sons_of="(.subj.*|aux|mark)"),
        Restriction(name="new_subj_opt", gov="(.?obj|nsubj.*)")
    ]])
    
    for advcl_restriction in [ambiguous_advcl_rest, ambiguous_advcl_rest_no_mark]:
        advcl_or_dep_propagation_per_type(sentence, advcl_restriction, "advcl", False, iids)


def extra_of_prep_alteration(sentence):
    of_prep_rest = Restriction(name="root", nested=[[
        Restriction(name="father", xpos="NN.*", nested=[[
            Restriction(name="nmod", xpos="NN.*", gov="nmod", nested=[[
                Restriction(gov="case", form="(?i:of)")
            ]])
        ]])
    ]])
    
    ret = match(sentence.values(), [[of_prep_rest]])
    if not ret:
        return
    
    for name_space in ret:
        father, _, _ = name_space['father']
        nmod, _, rel = name_space['nmod']
        nmod.add_edge(add_extra_info("compound", "nmod", phrase="of", prevs=rel), father)


def extra_compound_propagation(sentence):
    compound_rest = Restriction(name="father", nested=[[
        Restriction(name="middle_man", gov="(.obj|.subj.*)", xpos="NN.*", nested=[[
            Restriction(name="compound", gov="compound", xpos="NN.*")
        ]])
    ]])
    
    ret = match(sentence.values(), [[compound_rest]])
    if not ret:
        return
    
    for name_space in ret:
        father, _, _ = name_space['father']
        _, _, rel = name_space['middle_man']
        compound, _, _ = name_space['compound']
        pure_rel = split_by_at(rel)[0]
        if any([re.match("(.obj|.subj.*)", rel) for head, rel in compound.get_new_relations()]):
            continue
        compound.add_edge(add_extra_info(pure_rel, "compound", dep_type="NULL", uncertain=True, prevs=rel), father)


def extra_amod_propagation(sentence):
    amod_rest = Restriction(name="father", nested=[[
        Restriction(name="amod", gov="amod", no_sons_of="nsubj.*")
    ]])
    
    ret = match(sentence.values(), [[amod_rest]])
    if not ret:
        return
    
    for name_space in ret:
        father, _, _ = name_space['father']
        amod, _, rel = name_space['amod']
        father.add_edge(add_extra_info("nsubj", "amod", prevs=rel), amod)


def extra_acl_propagation(sentence):
    # part1: take care of all acl's that are marked by 'to'
    acl_to_rest = Restriction(name="root_or_so", nested=[[
        Restriction(name="verb", xpos="(VB.?)", nested=[[
            Restriction(name="subj", gov=".subj.*"),
            Restriction(name="father", diff="subj", nested=[[
                Restriction(name="acl", gov="acl(?!:relcl)", no_sons_of="nsubj.*", nested=[[
                    Restriction(name="to", gov="mark", xpos="TO")
                ]])
            ]])
        ]])
    ]])
    
    ret = match(sentence.values(), [[acl_to_rest]])
    if ret:
        for name_space in ret:
            subj, _, _ = name_space['subj']
            acl, _, rel = name_space['acl']
            subj.add_edge(add_extra_info("nsubj", "acl", dep_type="NULL", phrase='to', prevs=rel), acl)
    
    # part2: take care of all acl's that are not marked by 'to'
    acl_rest = Restriction(name="father", nested=[[
        Restriction(name="acl", gov="acl(?!:relcl)", no_sons_of="(nsubj.*|mark)")  # TODO: validate that mark can be here only 'to'.
    ]])
    
    ret = match(sentence.values(), [[acl_rest]])
    if not ret:
        return
    
    for name_space in ret:
        father, _, _ = name_space['father']
        acl, _, rel = name_space['acl']
        father.add_edge(add_extra_info("nsubj", "acl", dep_type="NULL", phrase="REDUCED", prevs=rel), acl)


def extra_dep_propagation(sentence, iids):
    dep_rest = Restriction(name="father", no_sons_of=".?obj", nested=[[
        Restriction(name="dep", gov="dep", no_sons_of=".subj.*"),
        Restriction(name="new_subj", gov="(nsubj.*)")
    ]])

    ambiguous_dea_rest = Restriction(name="father", nested=[[
        Restriction(name="dep", gov="dep", no_sons_of=".subj.*"),
        Restriction(name="new_subj_opt", gov="(.?obj|nsubj.*)")
    ]])
    
    for rest in [dep_rest, ambiguous_dea_rest]:
        advcl_or_dep_propagation_per_type(sentence, rest, "dep", True, iids)


# TODO - unify with other nmods props
def extra_subj_obj_nmod_propagation_of_nmods(sentence):
    rest = Restriction(name="receiver", nested=[[
        Restriction(name="mediator", gov="(dobj|.subj.*|nmod)", nested=[[
            Restriction(name="nmod", gov="nmod", nested=[
                [Restriction(name="like", gov="case", form="like")],
                [Restriction(name="such_as", gov="case", form="such", nested=[[
                    Restriction(gov="mwe", form="as")
                ]])],
                [Restriction(name="including", gov="case", form="including")]
            ])
        ]])
    ]])

    ret = match(sentence.values(), [[rest]])
    if not ret:
        return

    for name_space in ret:
        nmod, _, nmod_rel = name_space['nmod']
        receiver, _, _ = name_space['receiver']
        mediator_rel = name_space['mediator'][2]
        
        phrase = [prep for prep in ["like", "such_as", "including"] if prep in name_space][0]
        nmod.add_edge(add_extra_info(split_by_at(mediator_rel)[0], "nmod", phrase=phrase, prevs=mediator_rel), receiver)


def conj_propagation_of_nmods_per_type(sentence, rest, dont_check_precedence=False):
    ret = match(sentence.values(), [[rest]])
    if not ret:
        return

    # TODO: move this code to a global func, and share code with other cc-assignments
    cc_assignments = dict()
    for token in sentence.values():
        ccs = []
        for child, rel in sorted(token.get_children_with_rels(), reverse=True):
            if 'cc' == rel:
                ccs.append(child.get_conllu_field("form"))
        i = 0
        for child, rel in sorted(token.get_children_with_rels(), reverse=True):
            if rel.startswith('conj'):
                if len(ccs) == 0:
                    cc_assignments[child] = 'and'
                else:
                    cc_assignments[child] = ccs[i if i < len(ccs) else -1]
                i += 1
        
    for name_space in ret:
        nmod, _, nmod_rel = name_space['nmod']
        receiver, _, _ = name_space['receiver']
        conj, _, _ = name_space['conj'] if 'conj' in name_space else name_space['receiver']
        
        if '.' not in str(receiver.get_conllu_field("id")) and \
                (dont_check_precedence or nmod.get_conllu_field("id") > receiver.get_conllu_field("id")):
            nmod.add_edge(add_extra_info(split_by_at(nmod_rel)[0], "conj", uncertain=True, phrase=cc_assignments[conj], prevs=nmod_rel), receiver)


def extra_conj_propagation_of_nmods(sentence):
    son_rest = Restriction(name="receiver", no_sons_of="nmod", nested=[[
        Restriction(name="conj", gov="conj", nested=[[
            Restriction(name="nmod", gov="nmod(?!(.*@|:poss.*))")
        ]])
    ]])

    father_rest = Restriction(nested=[[
        Restriction(name="receiver", gov="conj"),  # TODO: validate no_sons_of="nmod" isn't needed.
        Restriction(name="nmod", gov="nmod(?!(.*@|:poss.*))")
    ]])
    
    for conj_restriction in [son_rest, father_rest]:
        conj_propagation_of_nmods_per_type(sentence, conj_restriction)


def extra_conj_propagation_of_poss(sentence):
    poss_rest = Restriction(nested=[[
        Restriction(name="receiver", no_sons_of="(nmod:poss.*|det)", gov="conj", xpos="(?!(PRP|NNP.?|WP))"),
        Restriction(name="nmod", gov="nmod:poss(?!.*@)")
    ]])
    
    conj_propagation_of_nmods_per_type(sentence, poss_rest, True)


# phenomena: indexicals
def extra_advmod_propagation(sentence):
    advmod_rest = Restriction(name="gov", nested=[[
        Restriction(name="middle_man", gov="(nmod.*)", nested=[[
            Restriction(name="advmod", gov="advmod", form=advmod_list),
            Restriction(name="case", gov="case")
        ]])
    ]])
    ret = match(sentence.values(), [[advmod_rest]])
    if not ret:
        return
    
    for name_space in ret:
        advmod, _, advmod_rel = name_space['advmod']
        _, _, middle_man_rel = name_space['middle_man']
        gov, _, _ = name_space['gov']
        case, _, _ = name_space['case']
        
        if gov not in advmod.get_parents():
            advmod.add_edge(add_extra_info(split_by_at(advmod_rel)[0], "nmod", dep_type="INDEXICAL", phrase=case.get_conllu_field("form"), uncertain=True, prevs=middle_man_rel), gov)


# Purpose: move preposition to the relation label including cases of multi word preposition
# Notes:
#   1. we don't want to catch "all in all" but it seems it  won't be caught by the current restriction structure anyway.
#   2. we don't want to catch "as much as" or any "as ADVMOD as-NMOD", hence the use of the aggressive no_sons_of
#   3. We wanted to split the cses according to the black list of advmod+nmod as they are treated differently
class NmodAdvmodReconstruction(ABC):
    @staticmethod
    def get_conv_type() -> ConvTypes:
        return ConvTypes.BART

    @staticmethod
    @abstractmethod
    def is_complex() -> bool:
        raise NotImplementedError
    
    @classmethod
    def get_restriction(cls) -> Restriction:
        return Restriction(name="gov", nested=[[
            Restriction(name="advmod", form_combo_in=(nmod_advmod_complex, ['case'], cls.is_complex()), no_sons_of="advmod", gov="advmod", nested=[[
                Restriction(name="nmod", gov=f"{udv('nmod', 'obl')}", nested=[[
                    Restriction(name="case", gov="case")
                ]])
            ]])
        ]])
    
    @staticmethod
    @abstractmethod
    def specific_rewrite(advmod, nmod, case, gov) -> None:
        raise NotImplementedError

    @classmethod
    def rewrite(cls, hit_ns: Dict[str, Tuple[Token, Token, str]], sentence: List[Token] = None) -> None:
        cls.specific_rewrite(**hit_ns)


class NmodAdvmodReconstructionBasic(NmodAdvmodReconstruction):
    @staticmethod
    def is_complex():
        return False

    @staticmethod
    def specific_rewrite(advmod, nmod, case, gov) -> None:
        mwe = advmod[0].get_conllu_field("form").lower() + "_" + case[0].get_conllu_field("form").lower()
        advmod[0].replace_edge(advmod[2], add_extra_info(split_by_at(case[2])[0], "advmod_prep"), gov[0], nmod[0])
        case[0].replace_edge(case[2], add_extra_info("mwe", "advmod_prep"), nmod[0], advmod[0])
        nmod[0].replace_edge(nmod[2], add_extra_info(add_eud_info(split_by_at(nmod[2])[0], mwe), "advmod_prep"), advmod[0], gov[0])


class NmodAdvmodReconstructionComplex(NmodAdvmodReconstruction):
    @staticmethod
    def is_complex():
        return True
    
    @staticmethod
    def specific_rewrite(advmod, nmod, case, gov) -> None:
        nmod[0].add_edge(add_extra_info(add_eud_info(split_by_at(nmod[2])[0], case[0].get_conllu_field("form").lower()), "advmod_prep"), gov[0])


def extra_appos_propagation(sentence):
    appos_rest = Restriction(name="gov", nested=[[
        Restriction(name="appos", gov="appos")
    ]])
    ret = match(sentence.values(), [[appos_rest]])
    if not ret:
        return
    
    for name_space in ret:
        appos, _, _ = name_space['appos']
        gov, _, _ = name_space['gov']
        
        for (gov_head, gov_in_rel) in gov.get_new_relations():
            if (gov_head, gov_in_rel) not in appos.get_new_relations():
                appos.add_edge(add_extra_info(split_by_at(gov_in_rel)[0], "appos", prevs=gov_in_rel), gov_head)
        
        for (gov_son, gov_out_rel) in gov.get_children_with_rels():
            if re.match("(acl|amod)", gov_out_rel) and (gov_son, gov_out_rel) not in appos.get_children_with_rels():
                gov_son.add_edge(add_extra_info(split_by_at(gov_out_rel)[0], "appos", prevs=gov_out_rel), appos)


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
        closest_cc.replace_edge("cc", "cc", noun, verb)


# Purpose: TODO
# Notes:
#   1. formerly we did this as long as we find what to change, and each time change only one match, instead of fixing all matches found each time.
#       As every change we did might effect what can be found next, and old relations that were matched might be out dated.
#       But since this was a bad practice: (a) we dont use the matching properly, and (b) we use while true which might run forever,
#       and (c) we didn't kept a record of any case that could be harmed.
#       So we reverted it to regular behavior. When we do find such a case, we should record it and handle it more appropriately
#   2. old_root's xpos restriction comes to make sure we catch only non verbal copulas to reconstruct
#       (even though it should have been 'aux' instead of 'cop').
#   3. we want to catch all instances at once (hence the use of 'all') of any possible (hence the use of 'opt') old_root's child.
class CopulaReconstruction:
    @staticmethod
    def get_restriction() -> Restriction:
        return Restriction(name="father", nested=[[
            Restriction(name="old_root", xpos="(?!(VB.?))", nested=[[
                Restriction(name="cop", gov="cop"),
                Restriction(opt=True, all=True, name='regular_children', xpos="?!(TO)",  # avoid catching to-mark
                            gov="discourse|punct|advcl|xcomp|ccomp|expl|parataxis|mark)"),
                Restriction(opt=True, all=True, name='subjs', gov="(.subj.*)"),
                # here catch to-mark or aux (hence VB), or advmod (hence W?RB) to transfer to the copula
                Restriction(opt=True, all=True, name='to_cop', gov="(mark|aux.*|advmod)", xpos="(TO|VB|W?RB)"),
                Restriction(opt=True, all=True, name='cases', gov="case"),
                Restriction(opt=True, all=True, name='conjs', gov="conj", xpos="(VB.?)"),  # xpos rest -> transfer only conjoined verbs to the STATE
                Restriction(opt=True, all=True, name='ccs', gov="cc")
            ]])
        ]])
    
    @staticmethod
    def rewrite(hit_ns: Dict[str, Tuple[Token, Token, str]], sentence: List[Token] = None) -> None:
        cop, _, cop_rel = hit_ns['cop']
        old_root = hit_ns['old_root'][0]
        
        # add STATE node or nominate the copula as new root if we shouldn't add new nodes
        if not g_remove_node_adding_conversions:
            new_id = cop.get_conllu_field('id') + 0.1
            new_root = cop.copy(new_id=new_id, form="STATE", lemma="_", upos="_", xpos="_", feats="_", head="_", deprel="_", deps=None)
            sentence[new_id] = new_root
            # 'cop' becomes 'ev' (for event/evidential) to the new root
            cop.replace_edge(cop_rel, "ev", old_root, new_root)
        else:
            new_root = cop
            new_root.remove_edge(cop_rel, old_root)

        # transfer old-root's outgoing relation to new-root
        for head, rel in old_root.get_new_relations():
            old_root.remove_edge(rel, head)
            new_root.add_edge(rel, head)

        # transfer all old-root's children that are to be transferred
        for child, _, rel in hit_ns['regular_children'] + hit_ns['subjs']:
            child.replace_edge(rel, rel, old_root, new_root)
        for cur_to_cop, _, rel in hit_ns['to_cop']:
            cur_to_cop.replace_edge(rel, rel, old_root, cop)
        for conj, _, rel in hit_ns['conjs']:
            conj.replace_edge(rel, rel, old_root, new_root)
            # find best 'cc' to attach the new root as compliance with the transferred 'conj'.
            attach_best_cc(conj, list(zip(*hit_ns['ccs']))[0], old_root, new_root)
        
        # only if old_root is an adjective
        if re.match("JJ.?", old_root.get_conllu_field("xpos")):
            # update old-root's outgoing relation: for each subj add a 'amod' relation to the adjective.
            for subj in hit_ns['subjs']:
                old_root.add_edge(add_extra_info("amod", "cop"), subj)
        
        # connect the old_root as son of the new_root with the proper complement
        old_root.add_edge("xcomp" if 'cases' not in hit_ns else udv("nmod", "obl"), new_root)


def extra_inner_weak_modifier_verb_reconstruction(sentence, cop_rest, evidential):
    # NOTE: we do this as long as we find what to change, and each time change only one match, instead of fixing all matches found each time.
    #   As every change we do might change what can be found next, and old relations that are matched might be out dated.
    #   But this is bad practice. we dont use the matching properly, and we use while true which might run forever!
    found = set()
    while True:
        ret = match(sentence.values(), [[cop_rest]])
        if not ret:
            return
        cur_found = [
            "".join([k + str(v[0].get_conllu_field("id")) + str(v[1].get_conllu_field("id") if v[1] else v[1]) + str(v[2]) for k, v in ns.items()])
            for ns in ret]
        if not any([ns not in found for ns in cur_found]):
            return
        
        # As we might catch unwanted constructions (which the matcher couldnt handle), we added this while to find the first true match.
        for i, name_space in enumerate(ret):
            found.add(cur_found[i])
            old_root, _, _ = name_space['old_root']
            # the evidential should be the predecessor of the STATE as the cop is (even though he is also the old root of the construct).
            predecessor, _, _ = name_space['cop'] if 'cop' in name_space else name_space['old_root']
            
            # The old_root's father cant be 'STATE' or connect via ev. as it means we were already handled.
            #   The old_root's children cant be 'xcomp'(+'JJ') or 'ccomp' as they are handled separately.
            if any((head.get_conllu_field("form") == "STATE") or (split_by_at(rel)[0] == 'ev') for head, rel in old_root.get_new_relations()):
                old_root = None
                predecessor = None
                continue
            else:
                break
        # this means we didnt find any good old_root
        if not old_root:
            return
        
        if not g_remove_node_adding_conversions:
            new_id = predecessor.get_conllu_field('id') + 0.1
            new_root = predecessor.copy(new_id=new_id, form="STATE", lemma="_", upos="_", xpos="_", feats="_", head="_", deprel="_", deps=None)
            sentence[new_id] = new_root
        else:
            new_root = predecessor

        # transfer old-root's outgoing relation to new-root
        for head, rel in old_root.get_new_relations():
            old_root.remove_edge(rel, head)
            new_root.add_edge(rel, head)

        # transfer all old-root's children that are to be transferred
        ccs = [cc_child for cc_child, cc_rel in old_root.get_children_with_rels() if cc_rel == "cc"]
        subjs = []
        new_out_rel = "xcomp"
        new_amod = old_root
        for child, rel in old_root.get_children_with_rels():
            if re.match("((.subj.*)|discourse|punct|advcl|xcomp|ccomp|expl|parataxis)", rel):
                # transfer any of the following children
                child.replace_edge(rel, rel, old_root, new_root)
                # store subj children for later
                if re.match("(.subj.*)", rel):
                    subjs.append(child)
                # since only non verbal xcomps children get here, this child becomes an amod connection candidate (see later on)
                elif (rel == "xcomp") and evidential:
                    new_amod = child
            elif rel == "mark":
                if child.get_conllu_field('xpos') != 'TO':
                    # transfer any non 'to' markers
                    child.replace_edge(rel, rel, old_root, new_root)
                elif not evidential:
                    # make the 'to' be the son of the 'be' evidential (instead the copula old).
                    child.replace_edge(rel, rel, old_root, predecessor)
                # else: child is 'to' but it is the evidential case, so no need to change it's father.
            elif re.match("(aux.*|advmod)", rel) and not evidential:
                # simply these are to be transferred only in the copula case, to the 'cop' itself, as it is in the evidential case.
                child.replace_edge(rel, rel, old_root, predecessor)
            elif re.match("(case)", rel):
                new_out_rel = "nmod"
            elif "cop" == rel:
                if g_remove_node_adding_conversions:
                    child.remove_edge(rel, old_root)
                else:
                    # 'cop' becomes 'ev' (for event/evidential) to the new root
                    child.replace_edge(rel, "ev", old_root, new_root)
            elif ("conj" == rel) and re.match("(VB.?)", child.get_conllu_field("xpos")) and not evidential:
                # transfer 'conj' only if it is a verb conjunction, as we want it to be attached to the new (verb/state) root
                child.replace_edge(rel, rel, old_root, new_root)
                # find best 'cc' to attach the new root as compliance with the transferred 'conj'.
                attach_best_cc(child, ccs, old_root, new_root)
            elif re.match("nmod(?!:poss)", rel) and evidential:
                child.replace_edge(rel, rel, old_root, new_root)
            # else: {'compound', 'nmod', 'acl:relcl', 'amod', 'det', 'nmod:poss', 'nummod', 'nmod:tmod', some: 'cc', 'conj'}
        
        # update old-root's outgoing relation: for each subj add a 'amod' relation to the adjective.
        #   new_amod can be the old_root if it was a copula construct, or the old_root's 'xcomp' son if not.
        if re.match("JJ.?", new_amod.get_conllu_field("xpos")):
            for subj in subjs:
                new_amod.add_edge(add_extra_info("amod", "cop"), subj)
        
        # connect the old_root as son of the new_root as 'ev' if it was an evidential root,
        # or with the proper complement if it was an adjectival root under the copula construct
        old_root.add_edge('ev' if evidential else new_out_rel, new_root)


def per_type_weak_modified_verb_reconstruction(sentence, rest, type_, ccomp_case):
    # Copied NOTE from extra_inner_weak_modifier_verb_reconstruction: we do this as long as we find what to change,
    #   and each time change only one match,instead of fixing all matches found each time.
    #   As every change we do might change what can be found next, and old relations that are matched might be out dated.
    #   But this is bad practice. we dont use the matching properly, and we use while true which might run forever!
    found = set()
    while True:
        ret = match(sentence.values(), [[rest]])
        if not ret:
            return
        cur_found = ["".join([k + str(v[0].get_conllu_field("id")) + str(v[1].get_conllu_field("id") if v[1] else v[1]) + str(v[2]) for k, v in ns.items()]) for ns in ret]
        if not any([ns not in found for ns in cur_found]):
            return
        
        name_space = ret[0]
        found.add(cur_found[0])
        old_root, _, _ = name_space['old_root']
        new_root, _, _ = name_space['new_root']
        
        # transfer old-root's outgoing relation to new-root
        for head, rel in old_root.get_new_relations():
            old_root.remove_edge(rel, head)
            new_root.add_edge(rel, head)
        
        # transfer
        for child, rel in old_root.get_children_with_rels():
            if child == new_root:
                new_root.remove_edge(rel, old_root)
                # find lowest 'ev' of the new root, and make us his 'ev' son
                inter_root = new_root
                ev_sons = [c for c, r in inter_root.get_children_with_rels() if 'ev' == r.split('@')[0]]
                while ev_sons:
                    inter_root = ev_sons[0]  # TODO2: change to 'ev' son with lowest index?
                    if inter_root == new_root:
                        break
                    ev_sons = [c for c, r in inter_root.get_children_with_rels() if 'ev' == r.split('@')[0]]
                old_root.add_edge(add_extra_info('ev', rel, dep_type=type_), inter_root)
            elif rel == "mark":
                # see notes in copula
                if child.get_conllu_field('xpos') != 'TO':
                    child.replace_edge(rel, rel, old_root, new_root)  # TODO3: is this needed maybe all markers shouldnt be moved?
            elif re.match("(.subj.*)", rel):
                # transfer the subj only if it is not the special case of ccomp
                if not ccomp_case:
                    child.replace_edge(rel, rel, old_root, new_root)
            elif re.match("(?!advmod|aux.*|cc|conj).*", rel):
                child.replace_edge(rel, rel, old_root, new_root)  # TODO4: consult regarding all cases in the world.


def extra_evidential_reconstruction(sentence):
    # part1: find all evidential with no following(xcomp that is) main verb,
    #   and add a new node and transfer to him the rootness, like in copula
    # NOTE: we avoid the auxiliary sense of the evidential (in the 'be' case), with the gov restriction
    ev_rest = Restriction(name="father", nested=[[
        Restriction(name="old_root", gov="(?!aux.*).", xpos="(VB.?)", lemma=evidential_list, nested=[[
            Restriction(name="new_root", gov="(xcomp|nmod)", xpos="(JJ.*|NN.*)"),
        ]])
    ]])
    
    if not g_remove_node_adding_conversions:
        extra_inner_weak_modifier_verb_reconstruction(sentence, ev_rest, True)
    
    # part2: find all evidential with following(xcomp that is) main verb,
    #   and transfer to the main verb rootness
    # NOTE:
    #   1. xpos rest. avoids adjectives as we already treated them.
    ev_xcomp_rest = Restriction(name="father", nested=[[
        Restriction(name="old_root", xpos="(VB.?)", lemma=evidential_list, nested=[[
            Restriction(name="new_root", gov="xcomp", xpos="(?!(JJ.*|NN.*))"),
        ]])
    ]])

    per_type_weak_modified_verb_reconstruction(sentence, ev_xcomp_rest, "EVIDENTIAL", False)
    
    ev_ccomp_rest = Restriction(name="father", nested=[[
        Restriction(name="old_root", xpos="(VB.?)", lemma=evidential_list, nested=[[
            Restriction(name="new_root", gov="(ccomp)"),
        ]])
    ]])
    
    per_type_weak_modified_verb_reconstruction(sentence, ev_ccomp_rest, "EVIDENTIAL", True)


def extra_aspectual_reconstruction(sentence):
    aspect_xcomp_rest = Restriction(name="father", nested=[[
        Restriction(name="old_root", xpos="(VB.?)", lemma=aspectual_list, nested=[[
            Restriction(name="new_root", gov="xcomp", xpos="(?!JJ)"),
        ]])
    ]])
    
    per_type_weak_modified_verb_reconstruction(sentence, aspect_xcomp_rest, "ASPECTUAL", False)


def extra_reported_evidentiality(sentence):
    reported_rest = Restriction(name="father", nested=[[
        Restriction(name="ev", lemma=reported_list, nested=[[
            Restriction(name="new_root", gov="ccomp")
        ]])
    ]])
    
    ret = match(sentence.values(), [[reported_rest]])
    if not ret:
        return
    
    for name_space in ret:
        ev, _, _ = name_space['ev']
        new_root, _, _ = name_space['new_root']
        
        ev.add_edge(add_extra_info("ev", "ccomp", dep_type="REPORTED"), new_root)


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
def eudpp_process_simple_2wp(sentence):
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
def eudpp_process_complex_2wp(sentence):
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
def eudpp_process_3wp(sentence):
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
        [child.replace_edge(rel, rel, gov2_head, gov2) for (child, rel) in gov2_head.get_children_with_rels() if rel != "mwe"]


def eudpp_demote_quantificational_modifiers(sentence):
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
def add_ref_and_collapse_general(sentence, enhanced_plus_plus, enhanced_extra):
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
            leftmost_head, _, prevs_rel = name_space['mod']
            rels_with_pos = {(relation, child.get_conllu_field('xpos')): child.get_conllu_field('form') for (child, relation) in leftmost_head.get_children_with_rels()}
            rels_only = [rel for (rel, pos) in rels_with_pos.keys()]

            phrase = "REDUCED"
            if ("nsubj" not in rels_only) and ("nsubjpass" not in rels_only):
                leftmost_rel = 'nsubj'
            # some relativizers that were simply missing on the eUD.
            elif 'where' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = 'nmod'
                phrase = 'where'
            elif 'how' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = 'nmod'
                phrase = 'how'
            elif 'when' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = 'nmod:tmod'
                phrase = 'when'
            elif 'why' in [child.get_conllu_field('form') for child in leftmost_head.get_children()]:
                leftmost_rel = add_eud_info('nmod', 'because_of')
                phrase = 'why'
            
            # continue with *reduced* relcl, cased of orphan case/marker should become nmod and not obj
            elif ('nmod', 'RB') in rels_with_pos:
                leftmost_rel = add_eud_info('nmod', rels_with_pos[('nmod', 'RB')])
            elif ('advmod', 'RB') in rels_with_pos:
                leftmost_rel = add_eud_info('nmod', rels_with_pos[('advmod', 'RB')])
            elif ('nmod', 'IN') in rels_with_pos:
                leftmost_rel = add_eud_info('nmod', rels_with_pos[('nmod', 'IN')])
            
            # NOTE: I couldn't find an example for the following commented out very specific adjusment. TODO - remove in near future.
            # # this is a special case in which its not the head of the relative clause who get the nmod connection but one of its objects,
            # # as sometimes the relcl modifies the should-have-been-inner-object's-modifier
            # elif 'dobj' in rels_only:
            #     objs = [child for child, rel in leftmost_head.get_children_with_rels() if rel == 'dobj']
            #     found = False
            #     for obj in objs:
            #         rels_with_pos_obj = {(relation, child.get_conllu_field('xpos')): child for
            #                              (child, relation) in obj.get_children_with_rels()}
            #         if (('nmod', 'IN') in rels_with_pos_obj) or (('nmod', 'RB') in rels_with_pos_obj):
            #             case = rels_with_pos_obj[('nmod', 'IN')] if ('nmod', 'IN') in rels_with_pos_obj else rels_with_pos_obj[('nmod', 'RB')]
            #             gov.add_edge(add_extra_info(add_eud_info("nmod", case.get_conllu_field('form')), "reduced-relcl"), obj, extra_info=EXTRA_INFO_STUB)
            #             case.add_edge(add_extra_info("case", "reduced-relcl"), gov)
            #             found = True
            #             break
            #     if found:
            #         continue
            #     # this means we didn't find so rel should be dobj
            #     leftmost_rel = 'dobj'
            else:
                leftmost_rel = 'dobj'
            gov.add_edge(add_extra_info(leftmost_rel, "acl", dep_type="RELCL", phrase=phrase, prevs=prevs_rel), leftmost_head, extra_info=EXTRA_INFO_STUB)


def eudpp_add_ref_and_collapse(sentence):
    add_ref_and_collapse_general(sentence, True, False)


def extra_add_ref_and_collapse(sentence):
    add_ref_and_collapse_general(sentence, False, True)


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
def eud_conj_info(sentence):
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
        
        # Check if we already copied this node in this same match (as it is hard to restrict that).
        # This is relevant only for the prep type.
        if (not is_pp) and any(node.get_conllu_field("misc") == f"CopyOf={int(to_copy.get_conllu_field('id'))}" for node in sentence.values()):
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
def eudpp_expand_pp_or_prep_conjunctions(sentence):
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
def extra_fix_nmod_npmod(sentence):
    restriction = Restriction(nested=[[
        Restriction(name="npmod", gov="^nmod:npmod$")
    ]])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        npmod, npmod_head, npmod_rel = name_space['npmod']
        npmod.replace_edge(npmod_rel, "compound", npmod_head, npmod_head)


def extra_hyphen_reconstruction(sentence):
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
        subj, _, subj_rel = name_space['subj']
        verb, _, _ = name_space['verb']
        noun, _, noun_rel = name_space['noun']
        
        subj.add_edge(add_extra_info("nsubj", "compound", dep_type="HYPHEN", prevs=subj_rel), verb)
        noun.add_edge(add_extra_info("nmod", "compound", dep_type="HYPHEN", prevs=noun_rel), verb)


# The bottle was broken by me.
def extra_passive_alteration(sentence):
    restriction = Restriction(name="predicate", nested=[
        [
            Restriction(name="subjpass", gov=".subjpass"),
            Restriction(name="agent", gov="^(nmod(:agent)?)$", nested=[[
                Restriction(form="^(?i:by)$")
            ]])
        ],
        [Restriction(name="subjpass", gov=".subjpass")]
    ])
    
    ret = match(sentence.values(), [[restriction]])
    if not ret:
        return
    
    for name_space in ret:
        subj, _, subj_rel = name_space['subjpass']
        predicate, _, _ = name_space['predicate']
        if subj.match_rel(".obj", predicate):
            # avoid fixing a fixed passive.
            continue
        if 'agent' in name_space:
            agent, _, agent_rel = name_space['agent']
            agent.add_edge(add_extra_info("nsubj", "passive", prevs=agent_rel), predicate)
        
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
        
        subj.add_edge(add_extra_info(subj_new_rel, "passive", prevs=subj_rel), predicate)
    

def match_and_rewrite(sentence, class_name):
    for hit in match(sentence.values(), [[class_name.get_restriction()]]) or []:
        class_name.rewrite(hit, sentence)


def convert_sentence(sentence, iids):
    # The order of eud and eudpp is according to the order of the original CoreNLP (stanford-parser-full-2018-10-17\stanford-parser-3.9.2-sources\edu\stanford\nlp\trees\UniversalEnglishGrammaticalStructure.java).
    # The extra are our enhancements in which been added where we thought it best.

    match_and_rewrite(sentence, CorrectSubjPass)

    eudpp_process_simple_2wp(sentence)  # processMultiwordPreps: processSimple2WP
    eudpp_process_complex_2wp(sentence)  # processMultiwordPreps: processComplex2WP
    eudpp_process_3wp(sentence)  # processMultiwordPreps: process3WP
    eudpp_demote_quantificational_modifiers(sentence)  # demoteQuantificationalModifiers

    match_and_rewrite(sentence, NmodAdvmodReconstructionBasic)
    match_and_rewrite(sentence, NmodAdvmodReconstructionComplex)
    
    match_and_rewrite(sentence, CopulaReconstruction)
    extra_evidential_reconstruction(sentence)
    extra_aspectual_reconstruction(sentence)
    extra_reported_evidentiality(sentence)
    extra_fix_nmod_npmod(sentence)
    extra_hyphen_reconstruction(sentence)

    eudpp_expand_pp_or_prep_conjunctions(sentence)  # add copy nodes: expandPPConjunctions, expandPrepConjunctions

    match_and_rewrite(sentence, PassiveAgent)
    eud_heads_of_conjuncts(sentence)  # treatCC
    match_and_rewrite(sentence, PrepPatterns)
    eud_conj_info(sentence)  # addConjInformation

    extra_add_ref_and_collapse(sentence)
    eudpp_add_ref_and_collapse(sentence)  # referent: addRef, collapseReferent

    eud_subj_of_conjoined_verbs(sentence)  # treatCC
    eud_xcomp_propagation(sentence)  # addExtraNSubj

    extra_of_prep_alteration(sentence)
    extra_compound_propagation(sentence)
    extra_xcomp_propagation_no_to(sentence)
    extra_advcl_propagation(sentence, iids)
    extra_advcl_ambiguous_propagation(sentence, iids)
    extra_acl_propagation(sentence)
    extra_dep_propagation(sentence, iids)
    extra_conj_propagation_of_nmods(sentence)
    extra_conj_propagation_of_poss(sentence)
    extra_advmod_propagation(sentence)
    extra_appos_propagation(sentence)
    extra_subj_obj_nmod_propagation_of_nmods(sentence)
    extra_passive_alteration(sentence)
    
    return sentence


def override_funcs(enhanced, enhanced_plus_plus, enhanced_extra, remove_enhanced_extra_info, remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel):
    if not enhanced:
        funcs_to_cancel.update_funcs_by_prefix('eud_')
    if not enhanced_plus_plus:
        funcs_to_cancel.update_funcs_by_prefix('eudpp_')
    if not enhanced_extra:
        funcs_to_cancel.update_funcs_by_prefix('extra_')
    if remove_enhanced_extra_info:
        funcs_to_cancel.update_funcs(['eud_passive_agent', 'eud_conj_info'])
    if remove_node_adding_conversions:
        funcs_to_cancel.update_funcs(['eudpp_expand_pp_or_prep_conjunctions'])  # no need to cancel extra_inner_weak_modifier_verb_reconstruction as we have a special treatment there
    if remove_unc:
        funcs_to_cancel.update_funcs(['extra_dep_propagation', 'extra_compound_propagation', 'extra_conj_propagation_of_poss', 'extra_conj_propagation_of_nmods', 'extra_advmod_propagation', 'extra_advcl_ambiguous_propagation'])
    if query_mode:
        all_funcs = ConvsCanceler.get_conversion_names()
        all_funcs.difference_update(['extra_nmod_advmod_reconstruction', 'extra_copula_reconstruction', 'extra_evidential_reconstruction', 'extra_inner_weak_modifier_verb_reconstruction', 'extra_aspectual_reconstruction', 'eud_correct_subj_pass', 'eud_passive_agent', 'eud_conj_info', 'eud_prep_patterns', 'eudpp_process_simple_2wp', 'eudpp_process_complex_2wp', 'eudpp_process_3wp', 'eudpp_demote_quantificational_modifiers'])
        funcs_to_cancel.update_funcs(all_funcs)
    
    funcs_to_cancel.override_funcs()


def get_rel_set(converted_sentences):
    return set([(head.get_conllu_field("form"), rel, tok.get_conllu_field("form")) for sent in converted_sentences for tok in sent.values() for (head, rel) in tok.get_new_relations()])


def on_last_iter_convs(sentence):
    # TODO: after refactoring, if the match and replace system is more concise
    #   maybe it would be better to simply check that the subject didnt cpme from an amod.
    extra_amod_propagation(sentence)
    return sentence


def convert(parsed, enhanced, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_enhanced_extra_info, remove_bart_extra_info, remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel, ud_version=1):
    global g_remove_enhanced_extra_info, g_remove_bart_extra_info, g_remove_node_adding_conversions, g_ud_version
    g_remove_enhanced_extra_info = remove_enhanced_extra_info
    g_remove_bart_extra_info = remove_bart_extra_info
    g_remove_node_adding_conversions = remove_node_adding_conversions
    g_ud_version = ud_version
    iids = dict()
    
    override_funcs(enhanced, enhanced_plus_plus, enhanced_extra, remove_enhanced_extra_info, remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel)
    
    # we iterate till convergence or till user defined maximum is reached - the first to come.
    converted_sentences = parsed
    i = 0
    while i < conv_iterations:
        last_converted_sentences = get_rel_set(converted_sentences)
        temp = []
        for sentence in converted_sentences:
            temp.append(convert_sentence(sentence, iids))
        converted_sentences = temp
        if get_rel_set(converted_sentences) == last_converted_sentences:
            break
        i += 1

    # here we run some conversions that we believe should run only once and after all other conversions
    temp = []
    for sent in converted_sentences:
        temp.append(on_last_iter_convs(sent))
    converted_sentences = temp
    
    funcs_to_cancel.restore_funcs()
    return converted_sentences, i
