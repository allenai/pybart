# conversions as been done by StanfordConverter (a.k.a SC) version TODO
# global nuances from their converter:
#   1. we always write to 'deps' (so at first we copy 'head'+'deprel' to 'deps'), while they sometimes write back to 'deprel'.
#   2. we think like a multi-graph, so we operate on every relation/edge between two nodes, while they on first one found.
#   3. we look for all fathers as we can have multiple fathers, while in SC they look at first one found.

import sys
import re
from collections import defaultdict
from math import copysign
import inspect
from typing import List, Dict, Callable, Any

from .constraints import *
from .matcher import *
from .graph_token import Label
from . import pybart_globals

from .new_matcher import Matcher, NamedConstraint
from dataclasses import dataclass

# constants   # TODO - english specific
nmod_advmod_complex = ["back_to", "back_in", "back_at", "early_in", "late_in", "earlier_in"]
two_word_preps_regular = {"across_from", "along_with", "alongside_of", "apart_from", "as_for", "as_from", "as_of", "as_per", "as_to", "aside_from", "based_on", "close_by", "close_to", "contrary_to", "compared_to", "compared_with", " depending_on", "except_for", "exclusive_of", "far_from", "followed_by", "inside_of", "irrespective_of", "next_to", "near_to", "off_of", "out_of", "outside_of", "owing_to", "preliminary_to", "preparatory_to", "previous_to", "prior_to", "pursuant_to", "regardless_of", "subsequent_to", "thanks_to", "together_with"}
two_word_preps_complex = {"apart_from", "as_from", "aside_from", "away_from", "close_by", "close_to", "contrary_to", "far_from", "next_to", "near_to", "out_of", "outside_of", "pursuant_to", "regardless_of", "together_with"}
three_word_preps = {"by_means_of", "in_accordance_with", "in_addition_to", "in_case_of", "in_front_of", "in_lieu_of", "in_place_of", "in_spite_of", "on_account_of", "on_behalf_of", "on_top_of", "with_regard_to", "with_respect_to"}
clause_relations = ["conj", "xcomp", "ccomp", "acl", "advcl", "acl:relcl", "parataxis", "appos", "list"]
quant_mod_3w = ['lot', 'assortment', 'number', 'couple', 'bunch', 'handful', 'litany', 'sheaf', 'slew', 'dozen', 'series', 'variety', 'multitude', 'wad', 'clutch', 'wave', 'mountain', 'array', 'spate', 'string', 'ton', 'range', 'plethora', 'heap', 'sort', 'form', 'kind', 'type', 'version', 'bit', 'pair', 'triple', 'total']
quant_mod_2w = ['lots', 'many', 'several', 'plenty', 'tons', 'dozens', 'multitudes', 'mountains', 'loads', 'pairs', 'tens', 'hundreds', 'thousands', 'millions', 'billions', 'trillions']
quant_mod_2w_det = ['some', 'all', 'both', 'neither', 'everyone', 'nobody', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'hundred', 'thousand', 'million', 'billion', 'trillion']
relativizing_word_regex = "(?i:that|what|which|who|whom|whose)"
neg_conjp_prev = ["if_not"]
neg_conjp_next = ["instead_of", "rather_than", "but_rather", "but_not"]
and_conjp_next = ["as_well", "but_also"]
advmod_list = ['here', 'there', 'now', 'later', 'soon', 'before', 'then', 'today', 'tomorrow', 'yesterday', 'tonight', 'earlier', 'early']
evidential_list = ['seem', 'appear', 'be', 'sound']
aspectual_list = ['begin', 'continue', 'delay', 'discontinue', 'finish', 'postpone', 'quit', 'resume', 'start', 'complete']
reported_list = ['report', 'say', 'declare', 'announce', 'tell', 'state', 'mention', 'proclaim', 'replay', 'point', 'inform', 'explain', 'clarify', 'define', 'expound', 'describe', 'illustrate', 'justify', 'demonstrate', 'interpret', 'elucidate', 'reveal', 'confess', 'admit', 'accept', 'affirm', 'swear', 'agree', 'recognise', 'testify', 'assert', 'think', 'claim', 'allege', 'argue', 'assume', 'feel', 'guess', 'imagine', 'presume', 'suggest', 'argue', 'boast', 'contest', 'deny', 'refute', 'dispute', 'defend', 'warn', 'maintain', 'contradict']
advcl_non_legit_markers = ["as", "so", "when", "if"]  # TODO - english specific
adj_pos = ["JJ", "JJR", "JJS"]
verb_pos = ["VB", "VBD", "VBG", "VBN", "VBP", "VBZ", "MD"]
noun_pos = ["NN", "NNS", "NNP", "NNPS"]
pron_pos = ["PRP", "PRP$", "WP", "WP$"]
subj_options = ["nsubj", "nsubjpass", "csubj", "csubjpass"]  # TODO - UDv1 = pass
obj_options = ["dobj", "iobj"]  # TODO - UDv1 = pass
EXTRA_INFO_STUB = 1
g_remove_node_adding_conversions = False
g_iids = dict()
g_cc_assignments = dict()
g_ud_version = 1  # default UD version we work with is 1


class ConvTypes(Enum):
    EUD = 1
    EUDPP = 2
    BART = 3


ConvFuncSignature = Callable[[Any, Any], None]


@dataclass
class Conversion:
    conv_type: ConvTypes
    constraint: Full
    transformation: ConvFuncSignature

    def __post_init__(self):
        self.name = self.transformation.__name__


def get_conversion_names():
    return {func_name for (func_name, _) in inspect.getmembers(sys.modules[__name__], inspect.isfunction)
            if (func_name.startswith("eud") or func_name.startswith("eudpp") or func_name.startswith("extra"))}


def udv(udv1_str: str, udv2_str: str) -> str:
    return udv1_str if g_ud_version == 1 else udv2_str


# This method corrects subjects of verbs for which we identified an auxpass,
# but didn't identify the subject as passive.
eud_correct_subj_pass_constraint = Full(
    tokens=[
        Token(id="aux"),
        Token(id="pred"),
        Token(id="subj"),
    ],
    edges=[
        Edge(child="aux", parent="pred", label=[HasLabelFromList(["auxpass"])]),  # TODO - UDv1 = pass
        Edge(child="subj", parent="pred", label=[HasLabelFromList(["nsubj", "csubj"])]),
    ],
    distances=[UptoDistance("subj", "aux", inf)]
)


def eud_correct_subj_pass(sentence, matches):
    # for every located subject add a 'pass' and replace in graph node
    for cur_match in matches:
        subj = cur_match.token("subj")
        pred = cur_match.token("pred")
        for subj_rel in cur_match.edge(subj, pred):
            new_rel = Label(subj_rel.replace("subj", "subjpass"))  # TODO - UDv1 = pass
            sentence[subj].replace_edge(Label(subj_rel), new_rel, sentence[pred], sentence[pred])


# add 'agent' to nmods if it is cased by 'by', and have an auxpass sibling
eud_passive_agent_constraint = Full(
    tokens=[
        Token(id="gov", outgoing_edges=[HasLabelFromList(["auxpass"])]),  # TODO - UDv1 = pass
        Token(id="mod"),
        Token(id="case", spec=[Field(field=FieldNames.WORD, value=["by"])]),  # TODO: english = by
    ],
    edges=[
        Edge(child="mod", parent="gov", label=[HasLabelFromList(["nmod"])]),  # TODO - UDv1 = nmod
        Edge(child="case", parent="mod", label=[HasLabelFromList(["case"])]),
    ]
)


def eud_passive_agent(sentence, matches):
    for cur_match in matches:
        mod = cur_match.token("mod")
        gov = cur_match.token("gov")
        for rel in cur_match.edge(mod, gov):
            sentence[mod].replace_edge(Label(rel), Label(rel, eud="agent"), sentence[gov], sentence[gov])


# This conversion adds the case information on the label.
# Note - Originally  SC took care of cases in which the words of a multi-word preposition were not adjacent,
#   but this is too rigorous as it should never happen, so we ignore this case.
eud_prep_patterns_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="mod"),
        Token(id="c1"),
        Token(id="c_nn", optional=True, spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
        Token(id="c_in", optional=True, spec=[Field(field=FieldNames.TAG, value=["IN"])]),
    ],
    edges=[
        Edge(child="mod", parent="gov", label=[HasLabelFromList(["advcl", "acl", "nmod"])]),  # TODO - UDv1 = nmod
        Edge(child="c1", parent="mod", label=[HasLabelFromList(["case", "mark"])]),
        Edge(child="c_in", parent="c1", label=[HasLabelFromList(["mwe"])]),  # TODO - UDv1 = mwe
        Edge(child="c_nn", parent="c1", label=[HasLabelFromList(["mwe"])]),  # TODO - UDv1 = mwe
    ],
)


def eud_prep_patterns(sentence, matches):
    for cur_match in matches:
        mod = cur_match.token("mod")
        gov = cur_match.token("gov")
        c1 = cur_match.token("c1")
        c_in = cur_match.token("c_in")
        c_nn = cur_match.token("c_nn")
        for rel in cur_match.edge(mod, gov):
            prep_sequence = "_".join([sentence[ci].get_conllu_field("form") for ci in [c1, c_nn, c_in] if ci != -1]).lower()
            sentence[mod].replace_edge(Label(rel), Label(rel, prep_sequence), sentence[gov], sentence[gov])


eud_heads_of_conjuncts_constraint = Full(
    tokens=[
        Token(id="new_gov"),
        Token(id="gov"),
        Token(id="dep")],
    edges=[
        Edge(child="gov", parent="new_gov", label=[HasLabelFromList(["/.*/"]), HasNoLabel("case"), HasNoLabel("mark")]),
        Edge(child="dep", parent="gov", label=[HasLabelFromList(["conj"])]),
    ],
)


def eud_heads_of_conjuncts(sentence, matches):
    for cur_match in matches:
        new_gov = cur_match.token("new_gov")
        gov = cur_match.token("gov")
        dep = cur_match.token("dep")
        
        for rel in cur_match.edge(gov, new_gov):
            # TODO: check if we can safely get rid of this:
            # # only if they dont fall under the relcl problem, propagate the relation
            # if (new_gov, rel) not in gov.get_extra_info_edges():
            sentence[dep].add_edge(Label(rel), sentence[new_gov])
        
        # TODO:
        #   for the trees of ambiguous "The boy and the girl who lived told the tale."
        #   we want in the future to add an optional subj relation
        #   P.S. one of the trees could be obtained by the Stanford parser by adding commas:
        #   "The boy and the girl, who lived, told the tale."


eud_case_sons_of_conjuncts_constraint = Full(
    tokens=[
        Token(id="modifier"),
        Token(id="new_son"),
        Token(id="gov"),
        Token(id="dep", outgoing_edges=[HasNoLabel("case"), HasNoLabel("mark")])],
    edges=[
        Edge(child="gov", parent="modifier", label=[HasLabelFromList(["acl", "acl:relcl", "advcl", "nmod"])]),  # TODO: english = relcl, UDv1 = nmod
        Edge(child="new_son", parent="gov", label=[HasLabelFromList(["case", "mark"])]),
        Edge(child="dep", parent="gov", label=[HasLabelFromList(["conj"])]),
    ],
)


def eud_case_sons_of_conjuncts(sentence, matches):
    for cur_match in matches:
        new_son = sentence[cur_match.token("new_son")]
        dep = sentence[cur_match.token("dep")]

        new_son.add_edge(Label("case"), dep)
        

# NOTE -  we propagate only subj (for now) as this is what SC stated:
#     cdm july 2010: This bit of code would copy a dobj from the first
#     clause to a later conjoined clause if it didn't
#     contain its own dobj or prepc. But this is too aggressive and wrong
#     if the later clause is intransitive
#     (including passivized cases) and so I think we have to not have this
#     done always, and see no good "sometimes" heuristic.
#     IF WE WERE TO REINSTATE, SHOULD ALSO NOT ADD OBJ IF THERE IS A ccomp (SBAR).
eud_subj_of_conjoined_verbs_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="conj", spec=[Field(field=FieldNames.TAG, value=adj_pos + verb_pos)],
              outgoing_edges=[HasNoLabel(subj_str) for subj_str in subj_options]),  # TODO - alternatively use regex
        Token(id="subj"),
        Token(id="auxpass", optional=True),
    ],
    edges=[
        Edge(child="subj", parent="gov", label=[HasLabelFromList(subj_options)]),
        Edge(child="conj", parent="gov", label=[HasLabelFromList(["conj"])]),
        Edge(child="auxpass", parent="conj", label=[HasLabelFromList(["auxpass"])]),  # TODO - UDv1 = pass
    ],
)


def eud_subj_of_conjoined_verbs(sentence, matches):
    for cur_match in matches:
        gov = cur_match.token("gov")
        conj = cur_match.token("conj")
        subj = cur_match.token("subj")
        auxpass = cur_match.token("auxpass")
        for rel in cur_match.edge(subj, gov):
            subj_rel = rel
            if subj_rel.endswith("subjpass") and auxpass == -1:
                subj_rel = subj_rel[:-4]
            elif subj_rel.endswith("subj") and auxpass != -1:
                subj_rel += "pass"
            sentence[subj].add_edge(Label(subj_rel), sentence[conj])


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
extra_xcomp_propagation_no_to_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="new_subj"),
        Token(id="xcomp", spec=[Field(field=FieldNames.TAG, value=verb_pos + adj_pos + ["TO"])],
              outgoing_edges=[HasNoLabel(subj) for subj in subj_options]),
        Token(id="to_marker", optional=True, spec=[Field(field=FieldNames.TAG, value=["TO"])]),
    ],
    edges=[
        Edge(child="xcomp", parent="gov", label=[HasLabelFromList(["xcomp"])]),
        Edge(child="to_marker", parent="xcomp", label=[HasLabelFromList(["mark", "aux"])]),
        Edge(child="new_subj", parent="gov", label=[HasLabelFromList(subj_options + obj_options)]),
    ],
)


def xcomp_propagation_per_type(sentence, matches, is_bart):
    labels_dict = defaultdict(list)
    for cur_match in matches:
        new_subj = cur_match.token("new_subj")
        xcomp = cur_match.token("xcomp")
        to_marker = cur_match.token("to_marker")
        gov = cur_match.token("gov")

        labels = cur_match.edge(new_subj, gov)
        labels_dict[(gov, xcomp, to_marker)].extend([(new_subj, label) for label in labels])

    for (gov, xcomp, to_marker), labels in labels_dict.items():
        obj_found = any("obj" in label for _, label in labels)
        for new_subj, label in labels:
            if obj_found and "subj" in label:
                continue
            is_xcomp_basic = (to_marker != -1) or (sentence[xcomp].get_conllu_field("xpos") == "TO")
            if is_xcomp_basic and not is_bart:
                sentence[new_subj].add_edge(Label("nsubj", eud="xcomp(INF)"), sentence[xcomp])
            elif not is_xcomp_basic and is_bart:
                sentence[new_subj].add_edge(Label("nsubj", src="xcomp", src_type="GERUND"), sentence[xcomp])


def eud_xcomp_propagation(sentence, matches):
    xcomp_propagation_per_type(sentence, matches, False)


def extra_xcomp_propagation_no_to(sentence, matches):
    xcomp_propagation_per_type(sentence, matches, True)


# propagate subject and(/or) object as (possible) subject(s) for the son of the `advcl` relation if it has no subject of his own
extra_advcl_propagation_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="dep", outgoing_edges=[HasNoLabel(value=subj_cur) for subj_cur in subj_options]),
        Token(id="subj"),
        Token(id="obj", optional=True),
        # we allow only a specified list of markers (or no marker at all) - according to research
        Token(id="mark", optional=True, spec=[Field(field=FieldNames.WORD, value=advcl_non_legit_markers, in_sequence=False)]),
    ],
    edges=[
        Edge(child="subj", parent="gov", label=[HasLabelFromList(subj_options)]),
        Edge(child="obj", parent="gov", label=[HasLabelFromList(obj_options)]),
        Edge(child="dep", parent="gov", label=[HasLabelFromList(["advcl"])]),
        Edge(child="mark", parent="dep", label=[HasLabelFromList(["mark", "aux"])]),
    ],
)


# propagate subject and(/or) object as (possible) subject(s) for the son of the `dep` relation if it has no subject of his own
extra_dep_propagation_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="dep", outgoing_edges=[HasNoLabel(value=subj_cur) for subj_cur in subj_options]),
        Token(id="subj"),
        Token(id="obj", optional=True),
        Token(id="mark", optional=True),
    ],
    edges=[
        Edge(child="subj", parent="gov", label=[HasLabelFromList(subj_options)]),
        Edge(child="obj", parent="gov", label=[HasLabelFromList(obj_options)]),
        Edge(child="dep", parent="gov", label=[HasLabelFromList(["dep"])]),
        Edge(child="mark", parent="dep", label=[HasLabelFromList(["mark", "aux"])]),
    ],
)


def advcl_or_dep_propagation_per_type(sentence, matches, type_, unc):
    global g_iids
    for cur_match in matches:
        dep = sentence[cur_match.token("dep")]
        subj = sentence[cur_match.token("subj")]
        obj = cur_match.token("obj")
        mark = cur_match.token("mark")

        # extract the phrase of the marker, if there is one
        phrase = sentence[mark].get_conllu_field("form") if mark != -1 else "NULL"
        
        # decide if we need ALTERNATIVES for the propagation. That is, if we have both subject and object to propagate we give them ALT=some_id,
        # unless marker was `to`, in which we propagate only the object as we do in the xcomp case.
        if obj == -1 or phrase == "to":  # TODO - english = to
            cur_iid = None
        else:
            # get the id for this token or update the global ids for this new one.
            if dep not in g_iids:
                g_iids[dep] = 0 if len(g_iids.values()) == 0 else (max(g_iids.values()) + 1)
            cur_iid = g_iids[dep]

        # decide wether to propagte both the subject or object or both according to the criteria mentioned before
        if phrase != "to" or obj == -1:
            subj.add_edge(Label("nsubj", src=type_, phrase=phrase, iid=cur_iid, uncertain=unc), dep)
        if obj != -1:
            sentence[obj].add_edge(Label("nsubj", src=type_, phrase=phrase, iid=cur_iid, uncertain=unc), dep)


def extra_advcl_propagation(sentence, matches):
    advcl_or_dep_propagation_per_type(sentence, matches, "advcl", False)


def extra_dep_propagation(sentence, matches):
    advcl_or_dep_propagation_per_type(sentence, matches, "dep", True)


# here we add a compound relation for each nmod:of relation between two nouns
extra_of_prep_alteration_constraint = Full(
    tokens=[
        Token(id="nmod_of", spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
        Token(id="gov", spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
        Token(id="case", spec=[Field(field=FieldNames.WORD, value=["of"])]),  # TODO - english = of
    ],
    edges=[
        Edge(child="case", parent="nmod_of", label=[HasLabelFromList(["case"])]),
        Edge(child="nmod_of", parent="gov", label=[HasLabelFromList(["nmod"])]),  # TODO - UDv1 = nmod
    ],
)


def extra_of_prep_alteration(sentence, matches):
    for cur_match in matches:
        gov = cur_match.token("gov")
        nmod_of = cur_match.token("nmod_of")
        sentence[nmod_of].add_edge(Label("compound", src="nmod", phrase="of"), sentence[gov])  # TODO - english = of


# here we propagate subjects and objects from the compounds parent down to the compound, if they both are nouns
extra_compound_propagation_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="middle_man", spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
        Token(id="compound", spec=[Field(field=FieldNames.TAG, value=noun_pos)],
              # TODO: this validates that the compound does not have the propagated relation,
              #  and since we dont know in advance which relation exactly is going to be propagated,
              #  we add a rigorous HasNoLabel constraint for each
              incoming_edges=[HasNoLabel(arg) for arg in subj_options + obj_options]),
    ],
    edges=[
        Edge(child="middle_man", parent="gov", label=[HasLabelFromList(subj_options + obj_options)]),
        Edge(child="compound", parent="middle_man", label=[HasLabelFromList(["compound"])]),  # TODO - UDv1 = nmod
    ],
)


def extra_compound_propagation(sentence, matches):
    for cur_match in matches:
        gov = cur_match.token("gov")
        compound = cur_match.token("compound")
        middle_man = cur_match.token("middle_man")
        for rel in cur_match.edge(middle_man, gov):
            sentence[compound].add_edge(Label(rel, src="compound", src_type="NULL", uncertain=True), sentence[gov])


# here we add a subject relation for each amod relation (but in the opposite direction)
extra_amod_propagation_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="amod", incoming_edges=[HasNoLabel(arg) for arg in subj_options]),
    ],
    edges=[
        Edge(child="amod", parent="gov", label=[HasLabelFromList(["amod"])]),
    ],
)


def extra_amod_propagation(sentence, matches):
    for cur_match in matches:
        gov = cur_match.token("gov")
        amod = cur_match.token("amod")
        sentence[gov].add_edge(Label("nsubj", src="amod"), sentence[amod])


# acl part1: take care of all acl's (not acl:relcl) that are marked by 'to'
# this case is pretty specific. it means that if we have a verb with subject and object and the object has an acl relation,
# the new subject connection would be between the verb's subject and the acl subordinate, and not from the acl head relation (the object).
extra_acl_to_propagation_constraint = Full(
    tokens=[
        Token(id="verb", spec=[Field(FieldNames.TAG, verb_pos)]),
        Token(id="subj", spec=[Field(FieldNames.TAG, pron_pos + noun_pos)]),
        # we dont want the object/proxy to be the same as `subj` itself
        Token(id="proxy", spec=[Field(FieldNames.TAG, pron_pos + noun_pos)], incoming_edges=[HasNoLabel(subj_cur) for subj_cur in subj_options]),
        Token(id="acl", spec=[Field(FieldNames.TAG, verb_pos)], outgoing_edges=[HasNoLabel(subj_cur) for subj_cur in subj_options]),
        Token(id="to", spec=[Field(FieldNames.TAG, ["TO"])])],
    edges=[
        Edge(child="subj", parent="verb", label=[HasLabelFromList(subj_options)]),
        Edge(child="proxy", parent="verb", label=[HasLabelFromList(obj_options)]),  # TODO - originally it was `.*` regex, what else could be here?
        Edge(child="acl", parent="proxy", label=[HasLabelFromList(["acl"])]),
        Edge(child="to", parent="acl", label=[HasLabelFromList(["mark"])])
    ],
)


def extra_acl_to_propagation(sentence, matches):
    for cur_match in matches:
        subj = sentence[cur_match.token("subj")]
        acl = sentence[cur_match.token("acl")]
        to = sentence[cur_match.token("to")]
        subj.add_edge(Label("nsubj", src="acl", src_type="NULL", phrase=to.get_conllu_field("form")), acl)


# acl part2: take care of all acl's (not acl:relcl) that are not marked by 'to'
extra_acl_propagation_constraint = Full(
    tokens=[
        Token(id="father", spec=[Field(FieldNames.TAG, pron_pos + noun_pos)],
              incoming_edges=[HasNoLabel(subj_cur) for subj_cur in subj_options + ["mark"]]),
        Token(id="acl", spec=[Field(FieldNames.TAG, verb_pos)], outgoing_edges=[HasNoLabel(subj_cur) for subj_cur in subj_options]),
    ],
    edges=[
        Edge(child="acl", parent="father", label=[HasLabelFromList(["acl"])]),
    ],
)


def extra_acl_propagation(sentence, matches):
    for cur_match in matches:
        father = sentence[cur_match.token("father")]
        acl = sentence[cur_match.token("acl")]
        father.add_edge(Label("nsubj", src="acl", src_type="NULL", phrase="REDUCED"), acl)


extra_subj_obj_nmod_propagation_of_nmods_constraint = Full(
    tokens=[
        Token(id="receiver"),
        Token(id="mediator", spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
        Token(id="modifier"),
        Token(id="specifier", optional=True, spec=[Field(FieldNames.WORD, ["like", "such", "including"])]),  # TODO: english = like/such/including
        # this is needed for the `such as` case, as it is a multi word preposition
        Token(id="as", optional=True, spec=[Field(FieldNames.WORD, ["as"])]),  # TODO: english = as
        Token(id="case", optional=True, spec=[Field(FieldNames.TAG, ["IN", "TO"])]),
    ],
    edges=[
        Edge(child="mediator", parent="receiver", label=[HasLabelFromList(subj_options + obj_options + ["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="modifier", parent="mediator", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="specifier", parent="modifier", label=[HasLabelFromList(["case"])]),
        Edge(child="as", parent="specifier", label=[HasLabelFromList(["mwe"])]),  # TODO: UDv1 = mwe
        Edge(child="case", parent="mediator", label=[HasLabelFromList(["case"])]),
    ],
)


def extra_subj_obj_nmod_propagation_of_nmods(sentence, matches):
    for cur_match in matches:
        modifier = cur_match.token("modifier")
        receiver = cur_match.token("receiver")
        mediator = cur_match.token("mediator")
        specifier = cur_match.token("specifier")
        case = cur_match.token("case")
        
        # build the phrase according to the specific specifier
        phrase = sentence[specifier].get_conllu_field("form")
        if phrase == "such":
            as_ = cur_match.token("as")
            # if no `as` case, then this is not really `such as`
            if as_ == -1:
                return
            phrase = phrase + "_" + sentence[as_].get_conllu_field("form")
        
        # we loop just in case there are more than one of object/subject/modifier relations between the receiver and mediator
        for label in cur_match.edge(mediator, receiver):
            sentence[modifier].add_edge(Label(label, src="nmod", phrase=phrase), sentence[receiver])
            # also propagate the attached case in case of modifier relation between the receiver and mediator
            if label == "nmod" and case != -1:  # TODO: UDv1 = nmod
                sentence[case].add_edge(
                    Label("case", eud=sentence[case].get_conllu_info("form").lower(), src="nmod", phrase=phrase), sentence[modifier])


def conj_propagation_of_nmods_per_type(sentence, matches, specific_nmod_rel):
    for cur_match in matches:
        nmod = sentence[cur_match.token("nmod")]
        receiver = sentence[cur_match.token("receiver")]
        conj = cur_match.token("conj")
        
        # this prevents propagating modifiers to added nodes
        if '.' not in str(receiver.get_conllu_field("id")):
            conj_per_type = sentence[conj] if conj != -1 else receiver
            nmod.add_edge(Label(specific_nmod_rel, src="conj", uncertain=True, phrase=g_cc_assignments[conj_per_type][1]), receiver)


extra_conj_propagation_of_nmods_backwards_constraint = Full(
    tokens=[
        Token(id="receiver", outgoing_edges=[HasNoLabel("nmod")]),  # TODO: UDv1 = nmod
        Token(id="conj"),
        Token(id="nmod"),
    ],
    edges=[
        Edge(child="conj", parent="receiver", label=[HasLabelFromList(["conj"])]),
        Edge(child="nmod", parent="conj", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
    ],
)


def extra_conj_propagation_of_nmods_backwards(sentence, matches):
    conj_propagation_of_nmods_per_type(sentence, matches, "nmod")# TODO: UDv1 = nmod


extra_conj_propagation_of_nmods_forward_constraint = Full(
    tokens=[
        Token(id="father"),
        # TODO: validate if HasNoLabel("nmod") is really needed.
        Token(id="receiver", outgoing_edges=[HasNoLabel("nmod")]),  # TODO: UDv1 = nmod
        Token(id="nmod"),
    ],
    edges=[
        Edge(child="receiver", parent="father", label=[HasLabelFromList(["conj"])]),
        Edge(child="nmod", parent="father", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
    ],
    distances=[
        # this will prevent the propagation to create a backward modifier relation
        UptoDistance("receiver", "nmod", inf)
    ]
)


def extra_conj_propagation_of_nmods_forward(sentence, matches):
    conj_propagation_of_nmods_per_type(sentence, matches, "nmod")# TODO: UDv1 = nmod



extra_conj_propagation_of_poss_constraint = Full(
    tokens=[
        Token(id="father"),
        # we need the spec, to prevent propagation of possessive modifiers to pronouns ("my her"), and to proper nouns ("his U.S.A"),
        # and the `det` restriction to prevent propagation of possessive modifiers to definite phrases ("my the man")
        Token(id="receiver", spec=[Field(field=FieldNames.TAG, value=pron_pos + ["NNP", "NNPS"], in_sequence=False)],
              outgoing_edges=[HasNoLabel("nmod:poss"), HasNoLabel("det")]),  # TODO: UDv1 = nmod
        Token(id="nmod"),
    ],
    edges=[
        Edge(child="receiver", parent="father", label=[HasLabelFromList(["conj"])]),
        Edge(child="nmod", parent="father", label=[HasLabelFromList(["nmod:poss"])]),  # TODO: UDv1 = nmod
    ],
)


def extra_conj_propagation_of_poss(sentence, matches):
    conj_propagation_of_nmods_per_type(sentence, matches, "nmod:poss")# TODO: UDv1 = nmod


# Here we connect directly the advmod to a predicate that is mediated by an nmod
# We do this for the set of advmods the corresponds to the phenomenon known as indexicals
extra_advmod_propagation_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="middle_man"),
        Token(id="advmod", spec=[Field(field=FieldNames.WORD, value=advmod_list)]),
        Token(id="case"),
    ],
    edges=[
        Edge(child="middle_man", parent="gov", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="advmod", parent="middle_man", label=[HasLabelFromList(["advmod"])]),
        Edge(child="case", parent="middle_man", label=[HasLabelFromList(["case"])]),
    ],
)


def extra_advmod_propagation(sentence, matches):
    for cur_match in matches:
        gov = cur_match.token("gov")
        case = cur_match.token("case")
        advmod = cur_match.token("advmod")
        sentence[advmod].add_edge(Label("advmod", src="nmod", src_type="INDEXICAL", phrase=sentence[case].get_conllu_field("form"), uncertain=True), sentence[gov])


# here we connect the nmod to a predicate which is mediated by an advmod,
# and forming a multi-word preposition from the combination of the advmod and current preposition
# "I went back to prison"
extra_nmod_advmod_reconstruction_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="nmod"),
        # reason for WORD constraint: we dont want to catch the phrase "all in all"
        # reason for outgoing constraint: we dont want to catch phrases like "as much as" (implemented a bit rigorously)
        Token(id="advmod", spec=[Field(field=FieldNames.WORD, value=["all"], in_sequence=False)],
              outgoing_edges=[HasNoLabel("advmod")]),
        Token(id="case"),
    ],
    edges=[
        Edge(child="advmod", parent="gov", label=[HasLabelFromList(["advmod"])]),
        Edge(child="nmod", parent="advmod", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="case", parent="nmod", label=[HasLabelFromList(["case"])]),
    ],
)


def extra_nmod_advmod_reconstruction(sentence, matches):
    for cur_match in matches:
        gov = sentence[cur_match.token("gov")]
        case = sentence[cur_match.token("case")]
        advmod = sentence[cur_match.token("advmod")]
        nmod = sentence[cur_match.token("nmod")]

        # validate that nmod and fov are not connected already
        if gov in nmod.get_parents():
            continue

        # here we split the rewrite step to two behviors, depending on the advmod+preposition concatination,
        # if it's not part of nmod_advmod_complex: we remove the advmod from the governor
        # and connect it as a multi word case to the nmod, and downgrade the original case to be its mwe son.
        # in any way we connect the nmod to the governor
        mwe = advmod.get_conllu_field("form").lower() + "_" + case.get_conllu_field("form").lower()
        if mwe in nmod_advmod_complex:
            nmod.add_edge(Label("nmod", eud=case.get_conllu_field("form").lower(), src="advmod_prep"), gov)  # TODO: UDv1 = nmod
        else:
            advmod.replace_edge(Label("advmod"), Label("case", src="advmod_prep"), gov, nmod)
            case.replace_edge(Label("case"), Label("mwe", src="advmod_prep"), nmod, advmod)
            nmod.replace_edge(Label("nmod"), Label("nmod", eud=mwe, src="advmod_prep"), advmod, gov)  # TODO: UDv1 = nmod


extra_appos_propagation_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="appos"),
        Token(id="gov_parent", optional=True),
        Token(id="gov_son", optional=True),
    ],
    edges=[
        Edge(child="gov", parent="gov_parent", label=[HasLabelFromList(["/.*/"])]),
        # This is a hand made list of legitimate sons to propagate - so it can be enlarged
        Edge(child="gov", parent="gov_son", label=[HasLabelFromList(["acl", "amod"])]),
        Edge(child="appos", parent="gov", label=[HasLabelFromList(["appos"])]),
    ],
)


def extra_appos_propagation(sentence, matches):
    for cur_match in matches:
        gov_parent = cur_match.token("gov_parent")
        gov_son = cur_match.token("gov_son")
        gov = cur_match.token("gov")
        appos = cur_match.token("appos")
        for label in cur_match.edge(gov, gov_parent):
            sentence[appos].add_edge(Label(label, src="appos"), sentence[gov_parent])
        for label in cur_match.edge(gov_son, gov):
            sentence[gov_son].add_edge(Label(label, src="appos"), sentence[appos])


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
# class CopulaReconstruction:
#     @staticmethod
#     def get_restriction() -> Restriction:
#         return Restriction(name="father", nested=[[
#             Restriction(name="old_root", xpos="(?!(VB.?))", nested=[[
#                 Restriction(name="cop", gov="cop"),
#                 Restriction(opt=True, all=True, name='regular_children', xpos="?!(TO)",  # avoid catching to-mark
#                             gov="discourse|punct|advcl|xcomp|ccomp|expl|parataxis|mark)"),
#                 Restriction(opt=True, all=True, name='subjs', gov="(.subj.*)"),
#                 # here catch to-mark or aux (hence VB), or advmod (hence W?RB) to transfer to the copula
#                 Restriction(opt=True, all=True, name='to_cop', gov="(mark|aux.*|advmod)", xpos="(TO|VB|W?RB)"),
#                 Restriction(opt=True, all=True, name='cases', gov="case"),
#                 Restriction(opt=True, all=True, name='conjs', gov="conj", xpos="(VB.?)"),  # xpos rest -> transfer only conjoined verbs to the STATE
#                 Restriction(opt=True, all=True, name='ccs', gov="cc")
#             ]])
#         ]])
#
#     @staticmethod
#     def rewrite(hit_ns: Dict[str, Tuple[Token, Token, str]], sentence: List[Token] = None) -> None:
#         cop, _, cop_rel = hit_ns['cop']
#         old_root = hit_ns['old_root'][0]
#
#         # add STATE node or nominate the copula as new root if we shouldn't add new nodes
#         if not g_remove_node_adding_conversions:
#             new_id = cop.get_conllu_field('id') + 0.1
#             new_root = cop.copy(new_id=new_id, form="STATE", lemma="_", upos="_", xpos="_", feats="_", head="_", deprel="_", deps=None)
#             sentence[new_id] = new_root
#             # 'cop' becomes 'ev' (for event/evidential) to the new root
#             cop.replace_edge(cop_rel, "ev", old_root, new_root)
#         else:
#             new_root = cop
#             new_root.remove_edge(cop_rel, old_root)
#
#         # transfer old-root's outgoing relation to new-root
#         for head, rel in old_root.get_new_relations():
#             old_root.remove_edge(rel, head)
#             new_root.add_edge(rel, head)
#
#         # transfer all old-root's children that are to be transferred
#         for child, _, rel in hit_ns['regular_children'] + hit_ns['subjs']:
#             child.replace_edge(rel, rel, old_root, new_root)
#         for cur_to_cop, _, rel in hit_ns['to_cop']:
#             cur_to_cop.replace_edge(rel, rel, old_root, cop)
#         for conj, _, rel in hit_ns['conjs']:
#             conj.replace_edge(rel, rel, old_root, new_root)
#             # find best 'cc' to attach the new root as compliance with the transferred 'conj'.
#             attach_best_cc(conj, list(zip(*hit_ns['ccs']))[0], old_root, new_root)
#             TODO:         g_cc_assignments[conj].replace_edge("cc", "cc", noun, verb)
#
#         # only if old_root is an adjective
#         if re.match("JJ.?", old_root.get_conllu_field("xpos")):
#             # update old-root's outgoing relation: for each subj add a 'amod' relation to the adjective.
#             for subj in hit_ns['subjs']:
#                 old_root.add_edge(Label("amod", src="cop"), subj)
#
#         # connect the old_root as son of the new_root with the proper complement
#         old_root.add_edge("xcomp" if 'cases' not in hit_ns else udv("nmod", "obl"), new_root)


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
            if any((head.get_conllu_field("form") == "STATE") or (rel.with_no_bart() == 'ev') for head, rel in old_root.get_new_relations()):
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
                g_cc_assignments[child][0].replace_edge("cc", "cc", old_root, new_root)
            elif re.match("nmod(?!:poss)", rel) and evidential:
                child.replace_edge(rel, rel, old_root, new_root)
            # else: {'compound', 'nmod', 'acl:relcl', 'amod', 'det', 'nmod:poss', 'nummod', 'nmod:tmod', some: 'cc', 'conj'}
        
        # update old-root's outgoing relation: for each subj add a 'amod' relation to the adjective.
        #   new_amod can be the old_root if it was a copula construct, or the old_root's 'xcomp' son if not.
        if re.match("JJ.?", new_amod.get_conllu_field("xpos")):
            for subj in subjs:
                new_amod.add_edge(Label("amod", src="cop"), subj)
        
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
                ev_sons = [c for c,r in inter_root.get_children_with_rels() if 'ev' == r.split('@')[0]]
                while ev_sons:
                    inter_root = ev_sons[0]  # TODO2: change to 'ev' son with lowest index?
                    if inter_root == new_root:
                        break
                    ev_sons = [c for c,r in inter_root.get_children_with_rels() if 'ev' == r.split('@')[0]]
                old_root.add_edge(Label('ev', src=rel, src_type=type_), inter_root)
            elif rel == "mark":
                # see notes in copula
                if child.get_conllu_field('xpos') != 'TO':
                    child.replace_edge(rel, rel, old_root, new_root) # TODO3: is this needed maybe all markers shouldnt be moved?
            elif re.match("(.subj.*)", rel):
                # transfer the subj only if it is not the special case of ccomp
                if not ccomp_case:
                    child.replace_edge(rel, rel, old_root, new_root)
            elif re.match("(?!advmod|aux.*|cc|conj).*", rel):
                child.replace_edge(rel, rel, old_root, new_root)  # TODO4: consult regarding all cases in the world.


def extra_copula_reconstruction(sentence):
    # NOTE: the xpos restriction comes to make sure we catch only non verbal copulas to reconstruct
    #   (even though it should have been 'aux' instead of 'cop')
    cop_rest = Restriction(name="father", nested=[[
        Restriction(name="old_root", xpos="(?!(VB.?))", nested=[[
            Restriction(name="cop", gov="cop"),
        ]])
    ]])

    extra_inner_weak_modifier_verb_reconstruction(sentence, cop_rest, False)


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


# TODO: documentation!
extra_reported_evidentiality_constraint = Full(
    tokens=[
        Token(id="ev", spec=[Field(field=FieldNames.LEMMA, value=reported_list)]),
        Token(id="new_root"),
    ],
    edges=[
        Edge(child="new_root", parent="ev", label=[HasLabelFromList(["ccomp"])]),
    ],
)


def extra_reported_evidentiality(sentence, matches):
    for cur_match in matches:
        ev = cur_match.token("ev")
        new_root = cur_match.token("new_root")
        sentence[ev].add_edge(Label("ev", src="ccomp", src_type="REPORTED"), sentence[new_root])


def create_mwe(words, head, rel):
    for i, word in enumerate(words):
        word.remove_all_edges()
        word.add_edge(rel, head)
        if 0 == i:
            head = word
            rel = Label("mwe")  # TODO: UDv1 = mwe


def reattach_children(old_head, new_head, new_rel=None, cond=None):
    [child.replace_edge(child_rel, new_rel if new_rel else child_rel, old_head, new_head) for
     (child, child_rel) in old_head.get_children_with_rels() if not cond or cond(child_rel)]


def reattach_parents(old_child, new_child, new_rel=None, rel_by_cond=lambda x, y, z: x if x else y):
    new_child.remove_all_edges()
    [(old_child.remove_edge(parent_rel, head), new_child.add_edge(rel_by_cond(new_rel, parent_rel, head), head))
     for (head, parent_rel) in old_child.get_new_relations()]


# for example The street is across from you.
# The following relations:
#   advmod(you-6, across-4)
#   case(you-6, from-5)
# would be replaced with:
#   case(you-6, across-4)
#   mwe(across-4, from-5)
eudpp_process_simple_2wp_constraint = Full(
    tokens=[
        Token(id="w1", no_children=True),
        Token(id="w2", no_children=True),
        Token(id="common_parent")],
    edges=[
        Edge(child="w1", parent="common_parent", label=[HasLabelFromList(["case", "advmod"])]),
        Edge(child="w2", parent="common_parent", label=[HasLabelFromList(["case"])])
    ],
    distances=[ExactDistance("w1", "w2", distance=0)],
    concats=[TokenPair(two_word_preps_regular, "w1", "w2")]
)


def eudpp_process_simple_2wp(sentence, matches):
    for cur_match in matches:
        common_parent = sentence[cur_match.token("common_parent")]
        w1 = sentence[cur_match.token("w1")]
        w2 = sentence[cur_match.token("w2")]

        # create multi word expression
        create_mwe([w1, w2], common_parent, Label("case"))


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
eudpp_process_complex_2wp_constraint = Full(
    tokens=[
        Token(id="w1"),
        Token(id="w2", no_children=True),
        Token(id="proxy")],
    edges=[
        Edge(child="proxy", parent="w1", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="w2", parent="proxy", label=[HasLabelFromList(["case"])])
    ],
    distances=[ExactDistance("w1", "w2", distance=0)],
    concats=[TokenPair(two_word_preps_complex, "w1", "w2")]
)


def eudpp_process_complex_2wp(sentence, matches):
    for cur_match in matches:
        w1 = sentence[cur_match.token("w1")]
        w2 = sentence[cur_match.token("w2")]
        proxy = sentence[cur_match.token("proxy")]

        # assuming its either and not both
        proxy_rel = list(cur_match.edge(cur_match.token("proxy"), cur_match.token("w1")))[0]

        # make the proxy the head of the phrase
        reattach_parents(w1, proxy, new_rel=Label(proxy_rel),
                         # choose the relation to the new head to be according to a list of labels
                         rel_by_cond=lambda x, y, z: x if y.base not in (clause_relations + ["root"]) else y)

        # reattach w1 sons to gov2.
        reattach_children(w1, proxy)
        
        # create multi word expression
        create_mwe([w1, w2], proxy, Label("case"))


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
eudpp_process_3wp_constraint = Full(
    tokens=[
        Token(id="w1", no_children=True),
        Token(id="w2"),
        Token(id="w3", no_children=True),
        Token(id="proxy")],
    edges=[
        Edge(child="proxy", parent="w2", label=[HasLabelFromList(["nmod", "acl", "advcl"])]),  # TODO: UDv1 = nmod
        Edge(child="w1", parent="w2", label=[HasLabelFromList(["case"])]),
        Edge(child="w3", parent="proxy", label=[HasLabelFromList(["case", "mark"])])
    ],
    distances=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "w3", distance=0)],
    concats=[TokenTriplet(three_word_preps, "w1", "w2", "w3")]
)


def eudpp_process_3wp(sentence, matches):
    for cur_match in matches:
        w1 = sentence[cur_match.token("w1")]
        w2 = sentence[cur_match.token("w2")]
        w3 = sentence[cur_match.token("w3")]
        proxy = sentence[cur_match.token("proxy")]

        # assuming its either and not both
        case = list(cur_match.edge(cur_match.token("w3"), cur_match.token("proxy")))[0]
        proxy_rel = list(cur_match.edge(cur_match.token("proxy"), cur_match.token("w2")))[0]

        # make the proxy the head of the phrase
        reattach_parents(w2, proxy, new_rel=Label(proxy_rel),
                         # fix acl to advcl if the new head is a verb, or to root if should be
                         rel_by_cond=lambda x, y, z: y if x.base not in ["acl", "advcl"] or y.base != "nmod" else
                         (Label("advcl") if z.get_conllu_field("xpos") in verb_pos and x.base == "acl" else x))

        # reattach w2 sons to gov2
        reattach_children(w2, proxy)
        
        # create multi word expression
        create_mwe([w1, w2, w3], proxy, Label(case))


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
def demote_per_type(sentence, matches):
    for cur_match in matches:
        gov2 = sentence[cur_match.token("gov2")]
        old_gov = sentence[cur_match.token("w1")]
        w2 = sentence[cur_match.token("w2")]
        w3 = cur_match.token("w3")
        det = cur_match.token("det")
        case = cur_match.token("case")

        words = [old_gov, w2]
        if w3 != -1:
            words += [sentence[w3]]
            # run over what we 'though' to be the old_gov, as this is a 3-word mwe
            old_gov = w2
        elif det != -1:
            # NOTE: this is not done in SC, but should have been by THE PAPER.
            # adding the following determiner to the mwe.
            words += [sentence[det]]

        reattach_parents(old_gov, gov2)
        create_mwe(words, gov2, Label("det", "qmod"))
        # TODO: consider bringing back the 'if statement': [... if rel in ["punct", "acl", "acl:relcl", "amod"]]
        reattach_children(old_gov, gov2, cond=lambda x: x.base != "mwe")  # TODO: UDv1 = mwe


eudpp_demote_quantificational_modifiers_3w_constraint = Full(
    tokens=[
        Token(id="w1", spec=[Field(FieldNames.WORD, ["a", "an"])]),  # TODO: english = a, an
        Token(id="w2", spec=[Field(FieldNames.WORD, quant_mod_3w)]),
        Token(id="w3", spec=[Field(FieldNames.WORD, ["of"])]),  # TODO: english = of
        Token(id="gov2", spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
    ],
    edges=[
        Edge(child="gov2", parent="w2", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="w1", parent="w2", label=[HasLabelFromList(["det"])]),
        Edge(child="w3", parent="gov2", label=[HasLabelFromList(["case"])]),
    ],
    distances=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "w3", distance=0)],
)


def eudpp_demote_quantificational_modifiers_3w(sentence, matches):
    demote_per_type(sentence, matches)


eudpp_demote_quantificational_modifiers_2w_constraint = Full(
    tokens=[
        Token(id="w1", spec=[Field(FieldNames.WORD, quant_mod_2w)]),
        Token(id="w2", spec=[Field(FieldNames.WORD, ["of"])]),  # TODO: english = of
        Token(id="gov2", outgoing_edges=[HasNoLabel("det")], spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
    ],
    edges=[
        Edge(child="gov2", parent="w1", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="w2", parent="gov2", label=[HasLabelFromList(["case"])]),
    ],
    distances=[ExactDistance("w1", "w2", distance=0)]
)


def eudpp_demote_quantificational_modifiers_2w(sentence, matches):
    demote_per_type(sentence, matches)


eudpp_demote_quantificational_modifiers_det_constraint = Full(
    tokens=[
        Token(id="w1", spec=[Field(FieldNames.WORD, quant_mod_2w_det)]),
        Token(id="w2", spec=[Field(FieldNames.WORD, ["of"])]),  # TODO: english = of
        Token(id="gov2", spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
        Token(id="det", optional=True),
        # Token(id="case", optional=True)
    ],
    edges=[
        Edge(child="gov2", parent="w1", label=[HasLabelFromList(["nmod"])]),  # TODO: UDv1 = nmod
        Edge(child="w2", parent="gov2", label=[HasLabelFromList(["case"])]),
        Edge(child="det", parent="gov2", label=[HasLabelFromList(["det"])]),
        # Edge(child="case", parent="w1", label=[HasLabelFromList(["case"])])
    ],
    distances=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "det", distance=0)]
)


def eudpp_demote_quantificational_modifiers_det(sentence, matches):
    demote_per_type(sentence, matches)


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
                leftmost_rel = Label('nmod', 'because_of')
                phrase = 'why'
            
            # continue with *reduced* relcl, cased of orphan case/marker should become nmod and not obj
            elif ('nmod', 'RB') in rels_with_pos:
                leftmost_rel = Label('nmod', rels_with_pos[('nmod', 'RB')])
            elif ('advmod', 'RB') in rels_with_pos:
                leftmost_rel = Label('nmod', rels_with_pos[('advmod', 'RB')])
            elif ('nmod', 'IN') in rels_with_pos:
                leftmost_rel = Label('nmod', rels_with_pos[('nmod', 'IN')])
            
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
            #             gov.add_edge(Label("nmod", eud=case.get_conllu_field('form'), src="reduced-relcl"), obj, extra_info=EXTRA_INFO_STUB)
            #             case.add_edge(Label("case", src="reduced-relcl"), gov)
            #             found = True
            #             break
            #     if found:
            #         continue
            #     # this means we didn't find so rel should be dobj
            #     leftmost_rel = 'dobj'
            else:
                leftmost_rel = 'dobj'
            gov.add_edge(Label(leftmost_rel, src="acl", src_type="RELCL", phrase=phrase), leftmost_head, extra_info=EXTRA_INFO_STUB)


def eudpp_add_ref_and_collapse(sentence):
    add_ref_and_collapse_general(sentence, True, False)


def extra_add_ref_and_collapse(sentence):
    add_ref_and_collapse_general(sentence, False, True)


# Adds the type of conjunction to all conjunct relations
eud_conj_info_constraint = Full(
    tokens=[
        Token(id="gov"),
        Token(id="conj")],
    edges=[
        Edge(child="conj", parent="gov", label=[HasLabelFromList(["conj"])]),
    ],
)


def eud_conj_info(sentence, matches):
    for cur_match in matches:
        gov = sentence[cur_match.token("gov")]
        conj = sentence[cur_match.token("conj")]

        if conj not in g_cc_assignments:
            continue
        
        for rel in cur_match.edge(cur_match.token("conj"), cur_match.token("gov")):
            conj.replace_edge(Label(rel), Label(rel, g_cc_assignments[conj][1]), gov, gov)


def create_new_node(sentence, to_copy, nodes_copied, last_copy_id):
    # create a copy node,
    nodes_copied = 1 if to_copy.get_conllu_field('id') != last_copy_id else nodes_copied + 1
    last_copy_id = to_copy.get_conllu_field('id')
    new_id = to_copy.get_conllu_field('id') + (0.1 * nodes_copied)
    
    copy_node = to_copy.copy(new_id=new_id, head="_", deprel="_", misc="CopyOf=%d" % to_copy.get_conllu_field('id'))
    sentence[new_id] = copy_node
    
    return copy_node, nodes_copied, last_copy_id


# Expands PPs with conjunctions such as in the sentence
# "Bill flies to France and from Serbia." by copying the verb
# that governs the prepositional phrase resulting in the following new or changed relations:
#   conj:and(flies, flies')
#   cc(flies, and)
#   nmod(flies', Serbia)
# while those where removed:
#   cc(France-4, and-5)
#   conj(France-4, Serbia-7)
eudpp_expand_pp_conjunctions_constraint = Full(
    tokens=[
        Token(id="to_copy"),
        Token(id="gov", outgoing_edges=[HasLabelFromList(["case", "mark"])]),
        Token(id="conj", outgoing_edges=[HasLabelFromList(["case", "mark"])]),
    ],
    edges=[
        Edge(child="gov", parent="to_copy", label=[HasLabelFromList(["nmod", "acl", "advcl"])]),
        Edge(child="conj", parent="gov", label=[HasLabelFromList(["conj"])]),
    ],
)


def eudpp_expand_pp_conjunctions(sentence, matches):
    nodes_copied = 0
    last_copy_id = -1
    for cur_match in matches:
        gov = sentence[cur_match.token('gov')]
        to_copy = sentence[cur_match.token('to_copy')]
        conj = sentence[cur_match.token('conj')]

        if conj not in g_cc_assignments:
            continue

        cc_tok, cc_rel = g_cc_assignments[conj]

        copy_node, nodes_copied, last_copy_id = create_new_node(sentence, to_copy, nodes_copied, last_copy_id)
        copy_node.add_edge(Label("conj", cc_rel), to_copy)

        # replace cc('gov', 'cc') with cc('to_copy', 'cc')
        # NOTE: this is not mentioned in THE PAPER, but is done in SC (and makes sense).
        cc_tok.replace_edge(Label("cc"), Label("cc"), gov, to_copy)

        for rel in cur_match.edge(cur_match.token('gov'), cur_match.token('to_copy')):
            # replace conj('gov', 'conj') with e.g nmod(copy_node, 'conj')
            conj.replace_edge(Label("conj"), Label(rel), gov, copy_node)


# expands prepositions with conjunctions such as in the sentence
# "Bill flies to and from Serbia." by copying the verb resulting
# in the following new relations:
#   conj:and(flies, flies')
#   nmod(flies', Serbia)
eudpp_expand_prep_conjunctions_constraint = Full(
    tokens=[
        Token(id="to_copy"),
        Token(id="already_copied", optional=True),
        Token(id="modifier"),
        Token(id="gov", outgoing_edges=[HasLabelFromList(["cc"])]),
        Token(id="conj"),
    ],
    edges=[
        Edge(child="modifier", parent="to_copy", label=[HasLabelFromList(["nmod", "acl", "advcl"])]),
        Edge(child="already_copied", parent="to_copy", label=[HasLabelFromList(["conj"])]),
        Edge(child="gov", parent="modifier", label=[HasLabelFromList(["case", "mark"])]),
        Edge(child="conj", parent="gov", label=[HasLabelFromList(["conj"])]),
    ],
)


def eudpp_expand_prep_conjunctions(sentence, matches):
    nodes_copied = 0
    last_copy_id = -1
    for cur_match in matches:
        to_copy = sentence[cur_match.token('to_copy')]
        conj = sentence[cur_match.token('conj')]
        modifier = sentence[cur_match.token('modifier')]
        already_copied = cur_match.token('already_copied')

        if conj not in g_cc_assignments:
            continue
        
        # Check if we already copied this node in this same match (as it is hard to restrict that).
        # This is relevant only for the prep type.
        if already_copied != -1 and \
                any(node.get_conllu_field("misc") == f"CopyOf={int(to_copy.get_conllu_field('id'))}" for node in sentence.values()):
            continue
        
        copy_node, nodes_copied, last_copy_id = create_new_node(sentence, to_copy, nodes_copied, last_copy_id)
        copy_node.add_edge(Label("conj", g_cc_assignments[conj][1]), to_copy)
        
        # copy relation from modifier to new node e.g nmod:from(copy_node, 'modifier')
        for rel in cur_match.edge(cur_match.token('modifier'), cur_match.token('to_copy')):
            modifier.add_edge(Label(rel, conj.get_conllu_field('form')), copy_node)


# TODO: UDv1 specific
# TODO: Documentation
extra_fix_nmod_npmod_constraint = Full(
    tokens=[
        Token(id="npmod"),
        Token(id="gov"),
    ],
    edges=[
        Edge(child="npmod", parent="gov", label=[HasLabelFromList(["nmod:npmod"])]),
    ],
)


def extra_fix_nmod_npmod(sentence, matches):
    for cur_match in matches:
        gov = cur_match.token("gov")
        npmod = cur_match.token("npmod")
        for rel in cur_match.edge(npmod, gov):
            sentence[npmod].replace_edge(Label(rel), Label("compound"), sentence[gov], sentence[gov])


# TODO - add documentation!
extra_hyphen_reconstruction_constraint = Full(
    tokens=[
        Token(id="subj"),
        Token(id="verb", spec=[Field(field=FieldNames.TAG, value=list(set(verb_pos) - {"VB"}))]),
        Token(id="hyphen", spec=[
            Field(field=FieldNames.TAG, value=["HYPH"]), Field(field=FieldNames.WORD, value=["-"])]),
        Token(id="noun", spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
    ],
    edges=[
        Edge(child="verb", parent="subj", label=[HasLabelFromList(["amod"])]),
        Edge(child="hyphen", parent="verb", label=[HasLabelFromList(["punct"])]),
        Edge(child="noun", parent="verb", label=[HasLabelFromList(["compound"])]),
    ],
)


def extra_hyphen_reconstruction(sentence, matches):
    for cur_match in matches:
        subj = cur_match.token("subj")
        verb = cur_match.token("verb")
        noun = cur_match.token("noun")
        sentence[subj].add_edge(Label("nsubj", src="compound", src_type="HYPHEN"), sentence[verb])
        sentence[noun].add_edge(Label("nmod", src="compound", src_type="HYPHEN"), sentence[verb])  # TODO - UDv1 = nmod


# The bottle was broken by me.
extra_passive_alteration_constraint = Full(
    tokens=[
        Token(id="predicate"),
        # the no-object lookup will prevent repeatedly converting this conversion
        Token(id="subjpass", incoming_edges=[HasNoLabel(obj) for obj in obj_options]),
        Token(id="agent", optional=True),
        Token(id="by", optional=True, spec=[Field(FieldNames.WORD, ["by"])]),  # TODO - english specific
        Token(id="predicates_obj", optional=True)],
    edges=[
        Edge(child="subjpass", parent="predicate", label=[HasLabelFromList(["nsubjpass", "csubjpass"])]),  # TODO - UDv1 = pass
        # TODO: maybe nmod:agent is redundant as we always look at the basic label and agent is part of EUD (afaik)
        Edge(child="agent", parent="predicate", label=[HasLabelFromList(["nmod", "nmod:agent"])]),  # TODO: UDv1 = nmod
        Edge(child="by", parent="agent", label=[HasLabelFromList(["case"])]),
        Edge(child="predicates_obj", parent="predicate", label=[HasLabelFromList(obj_options)]),
    ]
)


def extra_passive_alteration(sentence, matches):
    for cur_match in matches:
        subj = sentence[cur_match.token("subjpass")]
        predicate = sentence[cur_match.token("predicate")]
        agent = cur_match.token("agent")
        by = cur_match.token("by")
        predicates_obj = cur_match.token("predicates_obj")
        
        # reverse the agent to be subject
        if agent != -1 and by != -1:
            sentence[agent].add_edge(Label("nsubj", src="passive"), predicate)
        
        # what kind of object to assign
        # NOTE:
        #   when there is csubjpass, there are also theoretical cases in which the relation shouldn't be object,
        #   but xcomp/ccomp/advcl (depending on the markers). but I couldn't reproduce these cases so they have been removed
        subj_new_rel = "dobj" if predicates_obj == -1 else "iobj"  # TODO: UDv1 = obj

        # reverse the passivised subject
        subj.add_edge(Label(subj_new_rel, src="passive"), predicate)


######################################################################################################################################################


# TODO: english = this entire function
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
        return "and"  # TODO: english = and
    else:
        return cc.get_conllu_field('form')


# In case multiple coordination marker depend on the same governor
# the one that precedes the conjunct is appended to the conjunction relation or the
# first one if no preceding marker exists.
def assign_ccs_to_conjs(sentence):
    global g_cc_assignments
    g_cc_assignments = dict()
    for token in sentence.values():
        ccs = []
        for child, rel in sorted(token.get_children_with_rels(), reverse=True):
            if 'cc' == rel.base:
                ccs.append(child)
        i = 0
        for child, rel in sorted(token.get_children_with_rels(), reverse=True):
            if rel.base.startswith('conj'):
                if len(ccs) == 0:
                    g_cc_assignments[child] = (None, 'and')
                else:
                    cc = ccs[i if i < len(ccs) else -1]
                    g_cc_assignments[child] = (cc, get_assignment(sentence, cc))
                i += 1


def remove_funcs(conversions, enhanced, enhanced_plus_plus, enhanced_extra, remove_enhanced_extra_info, remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel):
    if not enhanced:
        conversions = {conversion.name: conversion for conversion in conversions if conversion.conv_type != ConvTypes.EUD}
    if not enhanced_plus_plus:
        conversions = {conversion.name: conversion for conversion in conversions if conversion.conv_type != ConvTypes.EUDPP}
    if not enhanced_extra:
        conversions = {conversion.name: conversion for conversion in conversions if conversion.conv_type != ConvTypes.BART}
    if remove_enhanced_extra_info:
        conversions.pop('eud_passive_agent')
        conversions.pop('eud_conj_info')
    if remove_node_adding_conversions:
        # no need to cancel extra_inner_weak_modifier_verb_reconstruction as we have a special treatment there
        conversions.pop('eudpp_expand_prep_conjunctions')
        conversions.pop('eudpp_expand_pp_conjunctions')
    if remove_unc:
        for func_name in ['extra_dep_propagation', 'extra_compound_propagation', 'extra_conj_propagation_of_poss', 'extra_conj_propagation_of_nmods_forward', 'extra_conj_propagation_of_nmods_backwards', 'extra_advmod_propagation', 'extra_advcl_ambiguous_propagation']:
            conversions.pop(func_name)
    if query_mode:
        for func_name in conversions.keys():
            if func_name in ['extra_nmod_advmod_reconstruction', 'extra_copula_reconstruction', 'extra_evidential_reconstruction', 'extra_inner_weak_modifier_verb_reconstruction', 'extra_aspectual_reconstruction', 'eud_correct_subj_pass', 'eud_passive_agent', 'eud_conj_info', 'eud_prep_patterns', 'eudpp_process_simple_2wp', 'eudpp_process_complex_2wp', 'eudpp_process_3wp', 'eudpp_demote_quantificational_modifiers']:
                conversions.pop(func_name)
    for func_to_cancel in funcs_to_cancel:
        conversions.pop(func_to_cancel)

    return conversions


def get_rel_set(converted_sentence):
    return set([(head.get_conllu_field("id"), rel.to_str(), tok.get_conllu_field("id")) for tok in converted_sentence.values() for (head, rel) in tok.get_new_relations()])


def convert_sentence(sentence: Dict[int, Token], conversions, matcher: Matcher, conv_iterations: int):
    last_converted_sentence = None
    i = 0
    on_last_iter = ["extra_amod_propagation"]
    do_last_iter = []
    # we iterate till convergence or till user defined maximum is reached - the first to come.
    while (i < conv_iterations) and (get_rel_set(sentence) != last_converted_sentence):
        last_converted_sentence = get_rel_set(sentence)
        sentence_as_list = [t for i, t in sentence.items() if i != 0]
        m = matcher(sentence_as_list)
        for conv_name in m.names():
            if conv_name in on_last_iter:
                do_last_iter.append(conv_name)
                continue
            matches = m.matches_for(conv_name)
            conversions[conv_name].transformation(sentence, matches)
        i += 1

    for conv_name in do_last_iter:
        sentence_as_list = [t for i, t in sentence.items() if i != 0]
        m = matcher(sentence_as_list)
        matches = m.matches_for(conv_name)
        conversions[conv_name].transformation(sentence, matches)

    return i


def init_conversions():
    # TODO - update Full to each constraint
    conversion_list = [
        Conversion(ConvTypes.EUD, eud_correct_subj_pass_constraint, eud_correct_subj_pass),
        Conversion(ConvTypes.EUDPP, eudpp_process_simple_2wp_constraint, eudpp_process_simple_2wp),
        Conversion(ConvTypes.EUDPP, eudpp_process_complex_2wp_constraint, eudpp_process_complex_2wp),
        Conversion(ConvTypes.EUDPP, eudpp_process_3wp_constraint, eudpp_process_3wp),
        Conversion(ConvTypes.EUDPP, eudpp_demote_quantificational_modifiers_3w_constraint, eudpp_demote_quantificational_modifiers_3w),
        Conversion(ConvTypes.EUDPP, eudpp_demote_quantificational_modifiers_2w_constraint, eudpp_demote_quantificational_modifiers_2w),
        Conversion(ConvTypes.EUDPP, eudpp_demote_quantificational_modifiers_det_constraint, eudpp_demote_quantificational_modifiers_det),
        Conversion(ConvTypes.BART, extra_nmod_advmod_reconstruction_constraint, extra_nmod_advmod_reconstruction),
        Conversion(ConvTypes.BART, Full(), extra_copula_reconstruction),
        Conversion(ConvTypes.BART, Full(), extra_evidential_reconstruction),
        Conversion(ConvTypes.BART, Full(), extra_aspectual_reconstruction),
        Conversion(ConvTypes.BART, extra_reported_evidentiality_constraint, extra_reported_evidentiality),
        Conversion(ConvTypes.BART, extra_fix_nmod_npmod_constraint, extra_fix_nmod_npmod),
        Conversion(ConvTypes.BART, extra_hyphen_reconstruction_constraint, extra_hyphen_reconstruction),
        Conversion(ConvTypes.EUDPP, eudpp_expand_pp_conjunctions_constraint, eudpp_expand_pp_conjunctions),
        Conversion(ConvTypes.EUDPP, eudpp_expand_prep_conjunctions_constraint, eudpp_expand_prep_conjunctions),
        Conversion(ConvTypes.EUD, eud_passive_agent_constraint, eud_passive_agent),
        Conversion(ConvTypes.EUD, eud_heads_of_conjuncts_constraint, eud_heads_of_conjuncts),
        Conversion(ConvTypes.EUD, eud_case_sons_of_conjuncts_constraint, eud_case_sons_of_conjuncts),
        Conversion(ConvTypes.EUD, eud_prep_patterns_constraint, eud_prep_patterns),
        Conversion(ConvTypes.EUD, eud_conj_info_constraint, eud_conj_info),
        Conversion(ConvTypes.BART, Full(), extra_add_ref_and_collapse),
        Conversion(ConvTypes.EUDPP, Full(), eudpp_add_ref_and_collapse),
        Conversion(ConvTypes.EUD, eud_subj_of_conjoined_verbs_constraint, eud_subj_of_conjoined_verbs),
        Conversion(ConvTypes.EUD, extra_xcomp_propagation_no_to_constraint, eud_xcomp_propagation),
        Conversion(ConvTypes.BART, extra_of_prep_alteration_constraint, extra_of_prep_alteration),
        Conversion(ConvTypes.BART, extra_compound_propagation_constraint, extra_compound_propagation),
        Conversion(ConvTypes.BART, extra_xcomp_propagation_no_to_constraint, extra_xcomp_propagation_no_to),
        Conversion(ConvTypes.BART, extra_advcl_propagation_constraint, extra_advcl_propagation),
        Conversion(ConvTypes.BART, extra_acl_to_propagation_constraint, extra_acl_to_propagation),
        Conversion(ConvTypes.BART, extra_acl_propagation_constraint, extra_acl_propagation),
        Conversion(ConvTypes.BART, extra_dep_propagation_constraint, extra_dep_propagation),
        Conversion(ConvTypes.BART, extra_conj_propagation_of_nmods_backwards_constraint, extra_conj_propagation_of_nmods_backwards),
        Conversion(ConvTypes.BART, extra_conj_propagation_of_nmods_forward_constraint, extra_conj_propagation_of_nmods_forward),
        Conversion(ConvTypes.BART, extra_conj_propagation_of_poss_constraint, extra_conj_propagation_of_poss),
        Conversion(ConvTypes.BART, extra_advmod_propagation_constraint, extra_advmod_propagation),
        Conversion(ConvTypes.BART, extra_appos_propagation_constraint, extra_appos_propagation),
        Conversion(ConvTypes.BART, extra_subj_obj_nmod_propagation_of_nmods_constraint, extra_subj_obj_nmod_propagation_of_nmods),
        Conversion(ConvTypes.BART, extra_passive_alteration_constraint, extra_passive_alteration),
        Conversion(ConvTypes.BART, extra_amod_propagation_constraint, extra_amod_propagation)
    ]

    return {conversion.name: conversion for conversion in conversion_list}


def convert(parsed, enhanced, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_enhanced_extra_info,
            remove_bart_extra_info, remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel, context=None, ud_version=1):
    global g_remove_node_adding_conversions, g_iids, g_ud_version
    pybart_globals.g_remove_enhanced_extra_info = remove_enhanced_extra_info
    pybart_globals.g_remove_bart_extra_info = remove_bart_extra_info
    g_remove_node_adding_conversions = remove_node_adding_conversions
    g_ud_version = ud_version

    conversions = init_conversions()
    remove_funcs(conversions, enhanced, enhanced_plus_plus, enhanced_extra, remove_enhanced_extra_info,
                 remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel)
    matcher = Matcher([NamedConstraint(conversion_name, conversion.constraint)
                       for conversion_name, conversion in conversions.items()], context)

    i = 0
    for sentence in parsed:
        g_iids = dict()
        assign_ccs_to_conjs(sentence)
        i = max(i, convert_sentence(sentence, conversions, matcher, conv_iterations))

    return parsed, i
