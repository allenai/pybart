# conversions as been done by StanfordConverter (a.k.a SC) version TODO
# global nuances from their converter:
#   1. we always write to 'deps' (so at first we copy 'head'+'deprel' to 'deps'), while they sometimes write back to 'deprel'.
#   2. we think like a multi-graph, so we operate on every relation/edge between two nodes, while they on first one found.
#   3. we look for all fathers as we can have multiple fathers, while in SC they look at first one found.

import sys
from collections import defaultdict
import inspect

from .constraints import *
from .graph_token import Label, TokenId
from .matcher import Matcher, NamedConstraint
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
relativizing_words = ["that", "what", "which", "who", "whom", "whose"]
relativizers_to_rel = {'where': "nmod:lmod", "how": "nmod", "when": "nmod:tmod", "why": "nmod"}
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
udv_map = {"nsubjpass": "nsubj:pass", "csubjpass": "csubj:pass", "auxpass": "aux:pass", "dobj": "obj", "mwe": "fixed",
           "nmod": "obl", "nmod:agent": "obl:agent", "nmod:tmod": "obl:tmod", "nmod:lmod": "obl:lmod"}


class ConvTypes(Enum):
    EUD = 1
    EUDPP = 2
    BART = 3


ConvFuncSignature = Callable[[Any, Any, Any], None]


@dataclass
class Conversion:
    conv_type: ConvTypes
    constraint: Full
    transformation: ConvFuncSignature

    def __post_init__(self):
        self.name = self.transformation.__name__


def get_eud_info(eud_str, converter):
    return eud_str if not converter.remove_enhanced_extra_info else None


def get_conversion_names():
    return {func_name for (func_name, _) in inspect.getmembers(sys.modules[__name__], inspect.isfunction)
            if (func_name.startswith("eud") or func_name.startswith("eudpp") or func_name.startswith("extra"))}


def create_mwe(words, head, rel, secondary_rel, converter):
    for i, word in enumerate(words):
        word.remove_all_edges()
        word.add_edge(rel, head)
        if 0 == i:
            head = word
            rel = Label(secondary_rel)


def reattach_children(old_head, new_head, new_rel=None, cond=None):
    [child.replace_edge(child_rel, new_rel if new_rel else child_rel, old_head, new_head) for
     (child, child_rels) in old_head.get_children_with_rels() for child_rel in child_rels if not cond or cond(child_rel)]


def reattach_parents(old_child, new_child, new_rel=None, rel_by_cond=lambda x, y, z: x if x else y):
    new_child.remove_all_edges()
    [(old_child.remove_edge(parent_rel, head), new_child.add_edge(rel_by_cond(new_rel, parent_rel, head), head))
     for (head, parent_rels) in list(old_child.get_new_relations()) for parent_rel in parent_rels]


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
    cc_cur_id = cc.get_conllu_field('id').major - 1
    prev_forms = "_".join([info.get_conllu_field('form') for (iid, info) in enumerate(sentence)
                           if (cc_cur_id - 1 == iid or cc_cur_id == iid)])
    next_forms = "_".join([info.get_conllu_field('form') for (iid, info) in enumerate(sentence)
                           if (cc_cur_id + 1 == iid) or (cc_cur_id == iid)])
    if next_forms in neg_conjp_next or prev_forms in neg_conjp_prev:
        return "negcc"
    elif (next_forms in and_conjp_next) or (cc.get_conllu_field('form') == '&'):
        return "and"  # TODO: english = and
    else:
        return cc.get_conllu_field('form')


# In case multiple coordination marker depend on the same governor
# the one that precedes the conjunct is appended to the conjunction relation or the
# first one if no preceding marker exists.
def assign_ccs_to_conjs(sentence, cc_assignments):
    for token in sentence:
        ccs = []
        for child, rels in sorted(token.get_children_with_rels(), reverse=True):
            for rel in rels:
                if 'cc' == rel.base:
                    ccs.append(child)
        i = 0
        for child, rels in sorted(token.get_children_with_rels(), reverse=True):
            for rel in rels:
                if rel.base.startswith('conj'):
                    if len(ccs) == 0:
                        cc_assignments[child] = (None, 'and')
                    else:
                        cc = ccs[i if i < len(ccs) else -1]
                        cc_assignments[child] = (cc, get_assignment(sentence, cc))
                    i += 1


# ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ #


def init_conversions(remove_node_adding_conversions, ud_version):
    def udv(udv1_str: str) -> str:
        # the replace is to take care for a unique case in which we get nmod but dont want the corresponding obl,
        # but rather obl:lmod. while in ud v1 we still want nmod and not nmod:lmod as it doesnt exist in version 1
        return udv1_str.replace(":lmod", "") if ud_version == 1 else udv_map.get(udv1_str, udv1_str)

    subj_options = ["nsubj", udv("nsubjpass"), "csubj", udv("csubjpass")]
    obj_options = [udv("dobj"), "iobj"]

    # This method corrects subjects of verbs for which we identified an auxpass,
    # but didn't identify the subject as passive.
    eud_correct_subj_pass_constraint = Full(
        tokens=[
            Token(id="aux"),
            Token(id="pred"),
            Token(id="subj"),
        ],
        edges=[
            Edge(child="aux", parent="pred", label=[HasLabelFromList([udv("auxpass")])]),
            Edge(child="subj", parent="pred", label=[HasLabelFromList(["nsubj", "csubj"])]),
        ],
        distances=[UptoDistance("subj", "aux", inf)]
    )

    def eud_correct_subj_pass(sentence, matches, converter):
        # for every located subject add a 'pass' and replace in graph node
        for cur_match in matches:
            subj = cur_match.token("subj")
            pred = cur_match.token("pred")
            for subj_rel in cur_match.edge(subj, pred):
                new_rel = Label(subj_rel.replace("subj", udv("nsubjpass")[1:]))
                sentence[subj].replace_edge(Label(subj_rel), new_rel, sentence[pred], sentence[pred])

    # This conversion adds the case information on the label.
    # and adds 'agent' to nmods if it is cased by 'by', and have an auxpass sibling
    # Note - Originally  SC took care of cases in which the words of a multi-word preposition were not adjacent,
    #   but this is too rigorous as it should never happen, so we ignore this case.
    eud_prep_patterns_constraint = Full(
        tokens=[
            Token(id="gov"),
            Token(id="mod"),
            Token(id="auxpass", optional=True),
            Token(id="c1"),
            Token(id="c_nn", optional=True, spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
            Token(id="c_in", optional=True, spec=[Field(field=FieldNames.TAG, value=["IN", "TO"])]),
        ],
        edges=[
            Edge(child="mod", parent="gov", label=[HasLabelFromList(["advcl", "acl", "nmod", "obl"])]),
            Edge(child="c1", parent="mod", label=[HasLabelFromList(["case", "mark"])]),
            Edge(child="c_in", parent="c1", label=[HasLabelFromList([udv("mwe")])]),
            Edge(child="c_nn", parent="c1", label=[HasLabelFromList([udv("mwe")])]),
            Edge(child="auxpass", parent="gov", label=[HasLabelFromList([udv("auxpass")])]),
        ],
    )

    def eud_prep_patterns(sentence, matches, converter):
        for cur_match in matches:
            mod = cur_match.token("mod")
            gov = cur_match.token("gov")
            c1 = cur_match.token("c1")
            c_in = cur_match.token("c_in")
            c_nn = cur_match.token("c_nn")
            auxpass = cur_match.token("auxpass")
            for rel in cur_match.edge(mod, gov):
                prep_sequence = "_".join([sentence[ci].get_conllu_field("form") for ci in [c1, c_nn, c_in] if ci != -1]).lower()
                if prep_sequence == "by" and auxpass != -1:  # TODO: english = by
                    prep_sequence = "agent"
                # TODO: this is because we constraint only on base string and not on Label or parts of it such as eud
                if any(r.eud is not None for h, rels in sentence[mod].get_new_relations(sentence[gov]) for r in rels):
                    continue
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

    def eud_heads_of_conjuncts(sentence, matches, converter):
        for cur_match in matches:
            new_gov = cur_match.token("new_gov")
            gov = cur_match.token("gov")
            dep = cur_match.token("dep")

            for rel in cur_match.edge(gov, new_gov):
                if sentence[gov].get_conllu_field("id") < sentence[new_gov].get_conllu_field("id") < sentence[dep].get_conllu_field("id"):
                    continue
                if (sentence[new_gov], rel) not in [(h, r.base) for (h, rels) in sentence[dep].get_new_relations() for r in rels]:
                    sentence[dep].add_edge(Label(rel), sentence[new_gov])

            # TODO:
            #   for the trees of ambiguous "The boy and the girl who lived told the tale."
            #   we want in the future to add an optional subj relation
            #   P.S. one of the trees could be obtained by the Stanford parser by adding commas:
            #   "The boy and the girl, who lived, told the tale."

    eud_case_sons_of_conjuncts_constraint = Full(
        tokens=[
            Token(id="new_son"),
            Token(id="gov"),
            Token(id="dep", outgoing_edges=[HasNoLabel(child) for child in ["aux", udv("auxpass"), "case", "mark"]])],
        edges=[
            Edge(child="new_son", parent="gov", label=[HasLabelFromList(["aux", udv("auxpass"), "case", "mark"])]),
            Edge(child="dep", parent="gov", label=[HasLabelFromList(["conj"])]),
        ],
    )

    def eud_case_sons_of_conjuncts(sentence, matches, converter):
        for cur_match in matches:
            new_son = sentence[cur_match.token("new_son")]
            gov = cur_match.token("gov")
            dep = sentence[cur_match.token("dep")]

            rel = list(cur_match.edge(cur_match.token("new_son"), gov))[0]
            new_son.add_edge(Label(rel), dep)

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
            Edge(child="auxpass", parent="conj", label=[HasLabelFromList([udv("auxpass")])]),
        ],
    )

    def eud_subj_of_conjoined_verbs(sentence, matches, converter):
        for cur_match in matches:
            gov = cur_match.token("gov")
            conj = cur_match.token("conj")
            subj = cur_match.token("subj")
            auxpass = cur_match.token("auxpass")
            for rel in cur_match.edge(subj, gov):
                subj_rel = rel
                if subj_rel.endswith(udv("nsubjpass")[1:]) and auxpass == -1:
                    subj_rel = subj_rel[:-4]
                elif subj_rel.endswith("subj") and auxpass != -1:
                    subj_rel += udv("nsubjpass")[len("nsubj"):]
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
            Token(id="xcomp", spec=[Field(field=FieldNames.TAG, value=verb_pos + ["TO", "IN"])],
                  outgoing_edges=[HasNoLabel(subj) for subj in subj_options] + [HasNoLabel("mark"), HasNoLabel("aux")]),
        ],
        edges=[
            Edge(child="xcomp", parent="gov", label=[HasLabelFromList(["xcomp"])]),
            Edge(child="new_subj", parent="gov", label=[HasLabelFromList(subj_options + obj_options)]),
        ],
    )

    extra_xcomp_propagation_constraint = Full(
        tokens=[
            Token(id="gov"),
            Token(id="new_subj"),
            Token(id="xcomp", spec=[Field(field=FieldNames.TAG, value=verb_pos)],
                  outgoing_edges=[HasNoLabel(subj) for subj in subj_options]),
            Token(id="to_marker", spec=[Field(field=FieldNames.TAG, value=["TO", "IN"])]),
        ],
        edges=[
            Edge(child="xcomp", parent="gov", label=[HasLabelFromList(["xcomp"])]),
            Edge(child="to_marker", parent="xcomp", label=[HasLabelFromList(["mark", "aux"])]),
            Edge(child="new_subj", parent="gov", label=[HasLabelFromList(subj_options + obj_options)]),
        ],
    )

    def xcomp_propagation_per_type(sentence, matches, converter):
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
                is_xcomp_basic = (to_marker != -1) or (sentence[xcomp].get_conllu_field("xpos") in ["TO", "IN"])
                if is_xcomp_basic:
                    sentence[new_subj].add_edge(Label("nsubj", eud=get_eud_info("xcomp(INF)", converter)), sentence[xcomp])
                elif not is_xcomp_basic:
                    sentence[new_subj].add_edge(Label("nsubj", src="xcomp", src_type="GERUND"), sentence[xcomp])

    def eud_xcomp_propagation(sentence, matches, converter):
        xcomp_propagation_per_type(sentence, matches, converter)

    def extra_xcomp_propagation_no_to(sentence, matches, converter):
        xcomp_propagation_per_type(sentence, matches, converter)

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

    def advcl_or_dep_propagation_per_type(sentence, matches, type_, unc, converter):
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
                if dep not in converter.iids:
                    converter.iids[dep] = 0 if len(converter.iids.values()) == 0 else (max(converter.iids.values()) + 1)
                cur_iid = converter.iids[dep]

            # decide wether to propagte both the subject or object or both according to the criteria mentioned before
            if phrase != "to" or obj == -1:
                subj.add_edge(Label("nsubj", src=type_, phrase=phrase, iid=cur_iid, uncertain=unc), dep)
            if obj != -1:
                sentence[obj].add_edge(Label("nsubj", src=type_, phrase=phrase, iid=cur_iid, uncertain=unc), dep)

    def extra_advcl_propagation(sentence, matches, converter):
        advcl_or_dep_propagation_per_type(sentence, matches, "advcl", False, converter)

    def extra_dep_propagation(sentence, matches, converter):
        advcl_or_dep_propagation_per_type(sentence, matches, "dep", True, converter)

    # here we add a compound relation for each nmod:of relation between two nouns
    extra_of_prep_alteration_constraint = Full(
        tokens=[
            Token(id="nmod_of", spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
            Token(id="gov", spec=[Field(field=FieldNames.TAG, value=noun_pos)]),
            Token(id="case", spec=[Field(field=FieldNames.WORD, value=["of"])]),  # TODO - english = of
        ],
        edges=[
            Edge(child="case", parent="nmod_of", label=[HasLabelFromList(["case"])]),
            # UD-versioning note: only nmod and not obl here because we are looking specifically for a nominal modifier
            Edge(child="nmod_of", parent="gov", label=[HasLabelFromList(["nmod"])]),
        ],
    )

    def extra_of_prep_alteration(sentence, matches, converter):
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
            Edge(child="compound", parent="middle_man", label=[HasLabelFromList(["compound"])]),
        ],
    )

    def extra_compound_propagation(sentence, matches, converter):
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
            Token(id="amod", outgoing_edges=[HasNoLabel(arg) for arg in subj_options]),
        ],
        edges=[
            Edge(child="amod", parent="gov", label=[HasLabelFromList(["amod"])]),
        ],
    )

    def extra_amod_propagation(sentence, matches, converter):
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

    def extra_acl_to_propagation(sentence, matches, converter):
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

    def extra_acl_propagation(sentence, matches, converter):
        for cur_match in matches:
            father = sentence[cur_match.token("father")]
            acl = sentence[cur_match.token("acl")]
            father.add_edge(Label("nsubj", src="acl", src_type="NULL", phrase="REDUCED"), acl)

    extra_subj_obj_nmod_propagation_of_nmods_constraint = Full(
        tokens=[
            Token(id="receiver"),
            Token(id="mediator", spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
            Token(id="modifier"),
            Token(id="specifier", spec=[Field(FieldNames.WORD, ["like", "such", "including"])]),  # TODO: english = like/such/including
            # this is needed for the `such as` case, as it is a multi word preposition
            Token(id="as", optional=True, spec=[Field(FieldNames.WORD, ["as"])]),  # TODO: english = as
            Token(id="case", optional=True, spec=[Field(FieldNames.TAG, ["IN", "TO"])]),
        ],
        edges=[
            Edge(child="mediator", parent="receiver", label=[HasLabelFromList(subj_options + obj_options + ["nmod", "obl"])]),
            # UD-versioning note: we are looking for a nominal elaboration/specification so no obl
            Edge(child="modifier", parent="mediator", label=[HasLabelFromList(["nmod"])]),
            Edge(child="specifier", parent="modifier", label=[HasLabelFromList(["case"])]),
            Edge(child="as", parent="specifier", label=[HasLabelFromList([udv("mwe")])]),
            Edge(child="case", parent="mediator", label=[HasLabelFromList(["case"])]),
        ],
    )

    def extra_subj_obj_nmod_propagation_of_nmods(sentence, matches, converter):
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
                if label in ["nmod", "obl"] and case != -1:
                    sentence[case].add_edge(
                        Label("case", eud=sentence[case].get_conllu_field("form").lower(), src=label, phrase=phrase), sentence[modifier])

    def conj_propagation_of_nmods_per_type(sentence, matches, converter, nmod_fathers_name):
        for cur_match in matches:
            nmod = cur_match.token("nmod")
            receiver = sentence[cur_match.token("receiver")]
            conj = cur_match.token("conj")
            case = cur_match.token("case")
            father = cur_match.token(nmod_fathers_name)

            # this prevents propagating modifiers to added nodes
            if receiver.get_conllu_field("id").minor:
                continue

            conj_per_type = sentence[conj] if conj != -1 else receiver
            # for simplicity we assume the target nmod/obl is the only one in between
            label = list(cur_match.edge(nmod, father))[0]
            sentence[nmod].add_edge(
                Label(label, eud=None if case == -1 else sentence[case].get_conllu_field("form").lower(),
                      src="conj", uncertain=True, phrase=converter.cc_assignments[conj_per_type][1] if conj_per_type in converter.cc_assignments else None), receiver)

    extra_conj_propagation_of_nmods_backwards_constraint = Full(
        tokens=[
            Token(id="receiver", outgoing_edges=[HasNoLabel("nmod"), HasNoLabel("obl")]),
            Token(id="conj"),
            Token(id="nmod"),
            Token(id="case")
        ],
        edges=[
            Edge(child="conj", parent="receiver", label=[HasLabelFromList(["conj"])]),
            Edge(child="nmod", parent="conj", label=[HasLabelFromList(["nmod", "obl"])]),
            Edge(child="case", parent="nmod", label=[HasLabelFromList(["case"])])
        ],
    )

    def extra_conj_propagation_of_nmods_backwards(sentence, matches, converter):
        conj_propagation_of_nmods_per_type(sentence, matches, converter, nmod_fathers_name="conj")

    extra_conj_propagation_of_nmods_forward_constraint = Full(
        tokens=[
            Token(id="father"),
            # TODO: validate if HasNoLabel("nmod") is really needed.
            Token(id="receiver", outgoing_edges=[HasNoLabel("nmod"), HasNoLabel("obl")]),
            Token(id="nmod"),
            Token(id="case")
        ],
        edges=[
            Edge(child="receiver", parent="father", label=[HasLabelFromList(["conj"])]),
            Edge(child="nmod", parent="father", label=[HasLabelFromList(["nmod", "obl"])]),
            Edge(child="case", parent="nmod", label=[HasLabelFromList(["case"])])
        ],
        distances=[
            # this will prevent the propagation to create a backward modifier relation
            UptoDistance("receiver", "nmod", inf)
        ]
    )

    def extra_conj_propagation_of_nmods_forward(sentence, matches, converter):
        conj_propagation_of_nmods_per_type(sentence, matches, converter, nmod_fathers_name="father")

    extra_conj_propagation_of_poss_constraint = Full(
        tokens=[
            Token(id="father"),
            # we need the spec, to prevent propagation of possessive modifiers to pronouns ("my her"), and to proper nouns ("his U.S.A"),
            # and the `det` restriction to prevent propagation of possessive modifiers to definite phrases ("my the man")
            Token(id="receiver", spec=[Field(field=FieldNames.TAG, value=pron_pos + ["NNP", "NNPS"], in_sequence=False)],
                  outgoing_edges=[HasNoLabel("nmod:poss"), HasNoLabel("det")]),
            Token(id="nmod"),
        ],
        edges=[
            Edge(child="receiver", parent="father", label=[HasLabelFromList(["conj"])]),
            Edge(child="nmod", parent="father", label=[HasLabelFromList(["nmod:poss"])]),
        ],
    )

    def extra_conj_propagation_of_poss(sentence, matches, converter):
        conj_propagation_of_nmods_per_type(sentence, matches, converter, nmod_fathers_name="father")

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
            Edge(child="middle_man", parent="gov", label=[HasLabelFromList(["nmod", "obl"])]),
            Edge(child="advmod", parent="middle_man", label=[HasLabelFromList(["advmod"])]),
            Edge(child="case", parent="middle_man", label=[HasLabelFromList(["case"])]),
        ],
    )

    def extra_advmod_propagation(sentence, matches, converter):
        for cur_match in matches:
            gov = cur_match.token("gov")
            case = cur_match.token("case")
            advmod = cur_match.token("advmod")
            # for simplicity we assume the target nmod/obl is the only one in between
            label = list(cur_match.edge(cur_match.token("middle_man"), gov))[0]
            sentence[advmod].add_edge(Label("advmod", src=label, src_type="INDEXICAL", phrase=sentence[case].get_conllu_field("form"), uncertain=True), sentence[gov])

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
            # UD-versioning note: here we specifically look for obl in udv2, as we want the modifier to modify an adverb
            Edge(child="nmod", parent="advmod", label=[HasLabelFromList([udv("nmod")])]),
            Edge(child="case", parent="nmod", label=[HasLabelFromList(["case"])]),
        ],
        concats=[
            TokenPair(two_word_preps_regular, "advmod", "case", in_set=False),
            TokenPair(two_word_preps_complex, "advmod", "case", in_set=False)
        ]
    )

    def extra_nmod_advmod_reconstruction(sentence, matches, converter):
        for cur_match in matches:
            gov = sentence[cur_match.token("gov")]
            case = sentence[cur_match.token("case")]
            advmod = sentence[cur_match.token("advmod")]
            nmod = sentence[cur_match.token("nmod")]

            # validate that nmod and gov are not connected already
            if gov in nmod.get_parents():
                continue

            # UD-versioning note: in case the new governor is not nominal, we want the new label to be obl
            if gov.get_conllu_field("xpos") not in noun_pos + pron_pos:
                new_label = udv("nmod")
            else:
                new_label = "nmod"

            # here we split the rewrite step to two behaviors, depending on the advmod+preposition concatenation,
            # if it's not part of nmod_advmod_complex: we remove the advmod from the governor
            # and connect it as a multi word case to the nmod, and downgrade the original case to be its mwe son.
            # in any way we connect the nmod to the governor
            mwe = advmod.get_conllu_field("form").lower() + "_" + case.get_conllu_field("form").lower()
            if mwe in nmod_advmod_complex:
                nmod.add_edge(Label(new_label, eud=get_eud_info(case.get_conllu_field("form").lower(), converter), src="advmod_prep"), gov)
            else:
                advmod.replace_edge(Label("advmod"), Label("case", src="advmod_prep"), gov, nmod)
                case.replace_edge(Label("case"), Label(udv("mwe"), src="advmod_prep"), nmod, advmod)
                nmod.replace_edge(Label(udv("nmod")), Label(new_label, eud=get_eud_info(mwe, converter), src="advmod_prep"), advmod, gov)

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
            Edge(child="gov_son", parent="gov", label=[HasLabelFromList(["acl", "amod", "case"])]),
            Edge(child="appos", parent="gov", label=[HasLabelFromList(["appos"])]),
        ],
    )

    def extra_appos_propagation(sentence, matches, converter):
        for cur_match in matches:
            gov_parent = cur_match.token("gov_parent")
            gov_son = cur_match.token("gov_son")
            gov = cur_match.token("gov")
            appos = cur_match.token("appos")
            for label in cur_match.edge(gov, gov_parent):
                sentence[appos].add_edge(Label(label, src="appos"), sentence[gov_parent])
            for label in cur_match.edge(gov_son, gov):
                sentence[gov_son].add_edge(Label(label, src="appos"), sentence[appos])

    def reattach_children_copula(old_root, new_root, cop, converter):
        subjs = []
        new_out_rel = "xcomp"
        for child, rels in old_root.get_children_with_rels():
            for rel in rels:
                # Note - transfer 'conj' only if it is a verb conjunction,
                #   as we want it to be attached to the new (verb/state) root
                if rel.base in subj_options + ["discourse", "punct", "advcl", "xcomp", "ccomp", "expl", "parataxis"] \
                        or (rel.base == "mark" and child.get_conllu_field('xpos') != 'TO') \
                        or (("conj" == rel.base) and (child.get_conllu_field("xpos") in verb_pos)):
                    # transfer any of the following children and any non 'to' markers
                    child.replace_edge(rel, rel, old_root, new_root)
                    # attach the best 'cc' to the new root as compliance with the transferred 'conj'
                    if child in converter.cc_assignments and converter.cc_assignments[child][0]:
                        converter.cc_assignments[child][0].replace_edge(Label("cc"), Label("cc"), old_root, new_root)
                    # store subj children for later
                    if rel.base in subj_options:
                        subjs.append(child)
                elif rel.base in ["mark", "aux", udv("auxpass"), "advmod"]:  # TODO: and not evidential:
                    # simply these are to be transferred to the 'cop' itself, as it is in the evidential case.
                    # and make the 'to' be the son of the 'be' evidential (instead the copula old).
                    child.replace_edge(rel, rel, old_root, cop)
                elif rel.base == "case":
                    new_out_rel = udv("nmod")
                elif rel.base == "cop":
                    if not remove_node_adding_conversions:
                        # 'cop' becomes 'ev' (for event/evidential) to the new root
                        child.replace_edge(rel, Label("ev"), old_root, new_root)
                # else: 'compound', 'nmod', 'acl:relcl', 'amod', 'det', 'nmod:poss', 'nummod', 'nmod:tmod', ('cc', 'conj')

        return subjs, new_out_rel, old_root

    def reattach_children_evidential(old_root, new_root, predecessor):
        subjs = []
        new_amod = None
        for child, rels in old_root.get_children_with_rels():
            for rel in rels:
                # Note - transfer 'conj' only if it is a verb conjunction,
                #   as we want it to be attached to the new (verb/state) root
                if rel.base in subj_options + ["discourse", "punct", "advcl", "xcomp", "ccomp", "expl", "parataxis", "conj", "cc"] \
                        or (rel.base == "mark" and child.get_conllu_field('xpos') != 'TO'):
                    # transfer any of the following children and any non 'to' markers
                    child.replace_edge(rel, rel, old_root, new_root)
                    # store subj children for later
                    if rel.base in subj_options:
                        subjs.append(child)
                    # since only non verbal xcomps children get here, this child becomes an amod connection candidate
                    elif rel.base == "xcomp":
                        new_amod = child
                elif rel.base == udv("nmod"):
                    child.replace_edge(rel, rel, old_root, new_root)
        return subjs, 'ev', new_amod

    def extra_inner_weak_modifier_verb_reconstruction(sentence, matches, evidential, converter):
        for cur_match in matches:
            cop = cur_match.token("cop")
            old_root = sentence[cur_match.token("old_root")]

            # the evidential should be the predecessor of the STATE as the cop is
            # (even though he is also the old root of the construct).
            predecessor = sentence[cop] if cop != -1 else old_root

            # add STATE node or nominate the copula as new root if we shouldn't add new nodes
            if not remove_node_adding_conversions:
                new_id = TokenId(predecessor.get_conllu_field('id').major,
                                 predecessor.get_conllu_field('id').minor + 1)
                if new_id in [t.get_conllu_field("id") for t in sentence]:
                    return
                new_root = predecessor.copy(
                    new_id=new_id, form="STATE", lemma="_", upos="_", xpos="_", feats="_", head="_", deprel="_", deps=None)
                sentence.append(new_root)
            else:
                new_root = predecessor

            # transfer old-root's parents to new-root
            reattach_parents(old_root, new_root)

            if evidential:
                subjs, new_out_rel, new_amod = reattach_children_evidential(old_root, new_root, predecessor)
            else:
                subjs, new_out_rel, new_amod = reattach_children_copula(old_root, new_root, predecessor, converter)

            # update old-root's outgoing relation: for each subj add a 'amod' relation to the adjective.
            #   new_amod can be the old_root if it was a copula construct, or the old_root's 'xcomp' son if evidential
            #   (if he had an xcomp son, otherwise new_amod will be None, so we validate).
            if new_amod and new_amod.get_conllu_field("xpos") in adj_pos:
                # update old-root's outgoing relation: for each subj add a 'amod' relation to the adjective.
                for subj in subjs:
                    new_amod.add_edge(Label("amod", src="cop"), subj)

            # connect the old_root as son of the new_root as 'ev' if it was an evidential root,
            # or with the proper complement if it was an adjectival root under the copula construct
            old_root.add_edge(Label(new_out_rel), new_root)

    # NOTE: the xpos restriction comes to make sure we catch only non verbal copulas to reconstruct
    #   (even though it should have been 'aux' instead of 'cop')
    extra_copula_reconstruction_constraint = Full(
        tokens=[
            Token(id="old_root", spec=[Field(field=FieldNames.TAG, value=verb_pos, in_sequence=False)]),
            Token(id="cop"),
        ],
        edges=[
            Edge(child="cop", parent="old_root", label=[HasLabelFromList(["cop"])]),
        ],
    )

    def extra_copula_reconstruction(sentence, matches, converter):
        extra_inner_weak_modifier_verb_reconstruction(sentence, matches, False, converter)

    # part1: find all evidential with no following(xcomp that is) main verb,
    #   and add a new node and transfer to him the rootness, like in copula
    # NOTE: we avoid the auxiliary sense of the evidential (in the 'be' case), with the gov restriction
    extra_evidential_basic_reconstruction_constraint = Full(
        tokens=[
            Token(id="old_root", incoming_edges=[HasNoLabel("aux"), HasNoLabel(udv("auxpass"))],
                  spec=[Field(field=FieldNames.TAG, value=verb_pos), Field(field=FieldNames.LEMMA, value=evidential_list)]),
            Token(id="new_root", spec=[Field(field=FieldNames.TAG, value=noun_pos + adj_pos)]),
        ],
        edges=[
            Edge(child="new_root", parent="old_root", label=[HasLabelFromList(["xcomp", udv("nmod")])]),
        ],
    )

    def extra_evidential_basic_reconstruction(sentence, matches, converter):
        if not remove_node_adding_conversions:
            extra_inner_weak_modifier_verb_reconstruction(sentence, matches, True, converter)

    def per_type_weak_modified_verb_reconstruction(sentence, matches, type_, converter):
        for cur_match in matches:
            old_root = sentence[cur_match.token('old_root')]
            new_root = sentence[cur_match.token('new_root')]

            # assume either xcomp or ccomp
            ccomp_or_xcomp = list(cur_match.edge(cur_match.token('new_root'), cur_match.token('old_root')))[0]

            # transfer old-root's parents to new-root
            reattach_parents(old_root, new_root)

            # transfer
            for child, rels in old_root.get_children_with_rels():
                for rel in rels:
                    if rel.base == "mark":
                        # see notes in copula
                        if child.get_conllu_field('xpos') != 'TO':
                            child.replace_edge(rel, rel, old_root, new_root)
                    elif rel.base in subj_options:
                        # transfer the subj only if it is not the special case of ccomp
                        if ccomp_or_xcomp != "ccomp":
                            child.replace_edge(rel, rel, old_root, new_root)
                    elif rel.base in ["advmod", "aux", udv("auxpass"), "cc", "conj"]:
                        child.replace_edge(rel, rel, old_root, new_root)  # TODO4: consult regarding all cases in the world.

            # find lowest 'ev' of the new root, and make us his 'ev' son
            inter_root = new_root
            ev_sons = [c for c, rels in inter_root.get_children_with_rels() for r in rels if 'ev' == r.base]
            while ev_sons:
                inter_root = ev_sons[0]  # TODO2: change to 'ev' son with lowest index?
                if inter_root == new_root:
                    break
                ev_sons = [c for c, rels in inter_root.get_children_with_rels() for r in rels if 'ev' == r.base]
            old_root.add_edge(Label('ev', src=ccomp_or_xcomp, src_type=type_), inter_root)

    # part2: find all evidential with following(xcomp that is) main verb,
    #   and transfer to the main verb rootness
    extra_evidential_xcomp_reconstruction_constraint = Full(
        tokens=[
            Token(id="old_root", spec=[
                Field(field=FieldNames.TAG, value=verb_pos), Field(field=FieldNames.LEMMA, value=evidential_list)]),
            Token(id="new_root", spec=[Field(field=FieldNames.TAG, value=noun_pos + adj_pos, in_sequence=False)]),
        ],
        edges=[
            Edge(child="new_root", parent="old_root", label=[HasLabelFromList(["xcomp", "ccomp"])])
        ],
    )

    def extra_evidential_xcomp_reconstruction(sentence, matches, converter):
        per_type_weak_modified_verb_reconstruction(sentence, matches, "EVIDENTIAL", converter)

    extra_aspectual_reconstruction_constraint = Full(
        tokens=[
            Token(id="old_root", spec=[
                Field(field=FieldNames.TAG, value=verb_pos), Field(field=FieldNames.LEMMA, value=aspectual_list)]),
            Token(id="new_root", spec=[Field(field=FieldNames.TAG, value=adj_pos, in_sequence=False)]),
        ],
        edges=[
            Edge(child="new_root", parent="old_root", label=[HasLabelFromList(["xcomp"])]),
        ],
    )

    def extra_aspectual_reconstruction(sentence, matches, converter):
        per_type_weak_modified_verb_reconstruction(sentence, matches, "ASPECTUAL", converter)

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

    def extra_reported_evidentiality(sentence, matches, converter):
        for cur_match in matches:
            ev = cur_match.token("ev")
            new_root = cur_match.token("new_root")
            sentence[ev].add_edge(Label("ev", src="ccomp", src_type="REPORTED"), sentence[new_root])

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

    def eudpp_process_simple_2wp(sentence, matches, converter):
        for cur_match in matches:
            common_parent = sentence[cur_match.token("common_parent")]
            w1 = sentence[cur_match.token("w1")]
            w2 = sentence[cur_match.token("w2")]

            # create multi word expression
            create_mwe([w1, w2], common_parent, Label("case"), udv("mwe"), converter)

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
            Edge(child="proxy", parent="w1", label=[HasLabelFromList(["nmod", "obl"])]),
            Edge(child="w2", parent="proxy", label=[HasLabelFromList(["case"])])
        ],
        distances=[ExactDistance("w1", "w2", distance=0)],
        concats=[TokenPair(two_word_preps_complex, "w1", "w2")]
    )

    def eudpp_process_complex_2wp(sentence, matches, converter):
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
            create_mwe([w1, w2], proxy, Label("case"), udv("mwe"), converter)

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
            Edge(child="proxy", parent="w2", label=[HasLabelFromList(["nmod", "obl", "acl", "advcl"])]),
            Edge(child="w1", parent="w2", label=[HasLabelFromList(["case"])]),
            Edge(child="w3", parent="proxy", label=[HasLabelFromList(["case", "mark"])])
        ],
        distances=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "w3", distance=0)],
        concats=[TokenTriplet(three_word_preps, "w1", "w2", "w3")]
    )

    def eudpp_process_3wp(sentence, matches, converter):
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
                             rel_by_cond=lambda x, y, z: y if x.base not in ["acl", "advcl"] or y.base not in ["nmod", "obl"] else
                             (Label("advcl") if z.get_conllu_field("xpos") in verb_pos and x.base == "acl" else x))

            # reattach w2 sons to gov2
            reattach_children(w2, proxy)

            # create multi word expression
            create_mwe([w1, w2, w3], proxy, Label(case), udv("mwe"), converter)

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
    def demote_per_type(sentence, matches, converter):
        for cur_match in matches:
            gov2 = sentence[cur_match.token("gov2")]
            old_gov = sentence[cur_match.token("w1")]
            w2 = sentence[cur_match.token("w2")]
            w3 = cur_match.token("w3")
            det = cur_match.token("det")

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
            create_mwe(words, gov2, Label("det", "qmod"), udv("mwe"), converter)
            # TODO: consider bringing back the 'if statement': [... if rel in ["punct", "acl", "acl:relcl", "amod"]]
            reattach_children(old_gov, gov2, cond=lambda x: x.base != udv("mwe"))

    eudpp_demote_quantificational_modifiers_3w_constraint = Full(
        tokens=[
            Token(id="w1", spec=[Field(FieldNames.WORD, ["a", "an"])]),  # TODO: english = a, an
            Token(id="w2", spec=[Field(FieldNames.WORD, quant_mod_3w)]),
            Token(id="w3", spec=[Field(FieldNames.WORD, ["of"])]),  # TODO: english = of
            Token(id="gov2", spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
        ],
        edges=[
            # UD-versioning note: no need to use obl as we expect a modifier of nouns (a word from a list)
            Edge(child="gov2", parent="w2", label=[HasLabelFromList(["nmod"])]),
            Edge(child="w1", parent="w2", label=[HasLabelFromList(["det"])]),
            Edge(child="w3", parent="gov2", label=[HasLabelFromList(["case"])]),
        ],
        distances=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "w3", distance=0)],
    )

    def eudpp_demote_quantificational_modifiers_3w(sentence, matches, converter):
        demote_per_type(sentence, matches, converter)

    eudpp_demote_quantificational_modifiers_2w_constraint = Full(
        tokens=[
            Token(id="w1", spec=[Field(FieldNames.WORD, quant_mod_2w)]),
            Token(id="w2", spec=[Field(FieldNames.WORD, ["of"])]),  # TODO: english = of
            Token(id="gov2", outgoing_edges=[HasNoLabel("det")], spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
        ],
        edges=[
            # UD-versioning note: no need to use obl as we expect a modifier of nouns (a word from a list)
            Edge(child="gov2", parent="w1", label=[HasLabelFromList(["nmod"])]),
            Edge(child="w2", parent="gov2", label=[HasLabelFromList(["case"])]),
        ],
        distances=[ExactDistance("w1", "w2", distance=0)]
    )

    def eudpp_demote_quantificational_modifiers_2w(sentence, matches, converter):
        demote_per_type(sentence, matches, converter)

    eudpp_demote_quantificational_modifiers_det_constraint = Full(
        tokens=[
            Token(id="w1", spec=[Field(FieldNames.WORD, quant_mod_2w_det)]),
            Token(id="w2", spec=[Field(FieldNames.WORD, ["of"])]),  # TODO: english = of
            Token(id="gov2", spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
            Token(id="det", optional=True),
        ],
        edges=[
            # UD-versioning note: no need to use obl as we expect a modifier of nouns (a word from a list)
            Edge(child="gov2", parent="w1", label=[HasLabelFromList(["nmod"])]),
            Edge(child="w2", parent="gov2", label=[HasLabelFromList(["case"])]),
            Edge(child="det", parent="gov2", label=[HasLabelFromList(["det"])]),
        ],
        distances=[ExactDistance("w1", "w2", distance=0), ExactDistance("w2", "det", distance=0)]
    )

    def eudpp_demote_quantificational_modifiers_det(sentence, matches, converter):
        demote_per_type(sentence, matches, converter)

    # Look for ref rules for a given word.
    # Unlike what was done in SC, we dont look through the grandchildren, but only through the children
    # of the acl:relcl dependency, and assume only one so we dont look for the leftmost. (as this is redundant)
    # If any children is a that/what/which/etc word, we take him as the dependent for the ref TypedDependency.
    # Then we collapse the referent relation such as follows. e.g.:
    # "The man that I love ... " dobj(love, that) -> ref(man, that) dobj(love, man)
    eudpp_add_ref_and_collapse_constraint = Full(
        tokens=[
            Token(id="relativizer", spec=[Field(FieldNames.WORD, relativizing_words + list(relativizers_to_rel.keys()))]),
            Token(id="gov"),
            Token(id="mod")
        ],
        edges=[
            Edge(child="mod", parent="gov", label=[HasLabelFromList(["acl:relcl"])]),  # TODO: english: relcl
            Edge(child="relativizer", parent="mod", label=[HasLabelFromList(["/.*/"])])
        ],
    )

    def eudpp_add_ref_and_collapse(sentence, matches, converter):
        for cur_match in matches:
            gov = sentence[cur_match.token('gov')]
            mod = sentence[cur_match.token('mod')]
            relativizer = sentence[cur_match.token('relativizer')]

            # this is a pretty basic case so we can assume only one label
            label = list(cur_match.edge(cur_match.token('relativizer'), cur_match.token('mod')))[0]
            text = relativizer.get_conllu_field("form").lower()
            # some relativizers that were simply missing on the eUD, we added them as nmods
            new_label = Label(udv(relativizers_to_rel[text]), eud=text if 1 == ud_version else "") if text in relativizers_to_rel else Label(label)

            reattach_children(relativizer, gov)
            relativizer.replace_edge(Label(label), Label("ref"), mod, gov)
            gov.add_edge(new_label, mod)

    # this is for reduce-relative-clause
    extra_add_ref_and_collapse_constraint = Full(
        tokens=[
            # this will prevent changing the non-reduced relcl
            Token(id="gov", outgoing_edges=[HasNoLabel("ref")]),
            Token(id="mod"),
            Token("subj", optional=True),
            Token("prep", optional=True, spec=[Field(FieldNames.TAG, ["RB", "IN"])])
        ],
        edges=[
            Edge(child="mod", parent="gov", label=[HasLabelFromList(["acl:relcl"])]),  # TODO: english: relcl
            Edge(child="subj", parent="mod", label=[HasLabelFromList(subj_options)]),
            Edge(child="prep", parent="mod", label=[HasLabelFromList(["advmod", udv("nmod"), "case", "mark"])]),
        ],
    )

    def extra_add_ref_and_collapse(sentence, matches, converter):
        for cur_match in matches:
            gov = sentence[cur_match.token('gov')]
            mod = sentence[cur_match.token('mod')]
            subj = cur_match.token('subj')
            prep = cur_match.token('prep')

            eud = None
            if subj == -1:
                leftmost_rel = "nsubj"
            # cased of orphan case/marker should become nmod and not obj
            elif prep != -1:
                leftmost_rel = udv("nmod")
                eud = sentence[prep].get_conllu_field("form").lower()
                # replace the orphan prep to ba a case relation
                # TODO: but actually this is a bit harsh,
                #   for example "after" and "before" should remain 'advmod', maybe refix it in future
                old_rel = list(cur_match.edge(prep, cur_match.token('mod')))[0]
                sentence[prep].replace_edge(Label(old_rel), Label("case"), mod, mod)
            else:
                leftmost_rel = udv("dobj")
            gov.add_edge(Label(leftmost_rel, eud=get_eud_info(eud, converter), src="acl", src_type="RELCL", phrase="REDUCED"), mod)

    # Adds the type of conjunction to all conjunct relations
    eud_conj_info_constraint = Full(
        tokens=[
            Token(id="gov"),
            Token(id="conj")],
        edges=[
            Edge(child="conj", parent="gov", label=[HasLabelFromList(["conj"])]),
        ],
    )

    def eud_conj_info(sentence, matches, converter):
        for cur_match in matches:
            gov = sentence[cur_match.token("gov")]
            conj = sentence[cur_match.token("conj")]

            if conj not in converter.cc_assignments:
                continue

            for rel in cur_match.edge(cur_match.token("conj"), cur_match.token("gov")):
                conj.replace_edge(Label(rel), Label(rel, converter.cc_assignments[conj][1]), gov, gov)

    def create_new_node(sentence, to_copy, nodes_copied, last_copy_id):
        # create a copy node,
        to_copy_id = to_copy.get_conllu_field('id')
        nodes_copied = 1 if to_copy_id != last_copy_id else nodes_copied + 1
        last_copy_id = to_copy_id
        new_id = TokenId(to_copy_id.major, to_copy_id.minor + nodes_copied)

        copy_node = to_copy.copy(new_id=new_id, head="_", deprel="_", misc=f"CopyOf={str(to_copy.get_conllu_field('id'))}")
        sentence.append(copy_node)

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
            Token(id="conj"),
            Token(id="already_copied", optional=True),
        ],
        edges=[
            Edge(child="gov", parent="to_copy", label=[HasLabelFromList(["nmod", "acl", "advcl"])]),
            Edge(child="conj", parent="gov", label=[HasLabelFromList(["conj"])]),
            Edge(child="already_copied", parent="to_copy", label=[HasLabelFromList(["conj"])]),
        ],
    )

    def eudpp_expand_pp_conjunctions(sentence, matches, converter):
        nodes_copied = 0
        last_copy_id = -1
        for cur_match in matches:
            gov = sentence[cur_match.token('gov')]
            to_copy = sentence[cur_match.token('to_copy')]
            conj = sentence[cur_match.token('conj')]
            already_copied = cur_match.token('already_copied')

            if conj not in converter.cc_assignments:
                continue

            # Check if we already copied this node in this same match (as it is hard to restrict that).
            if already_copied != -1 and \
                    any(node.get_conllu_field("misc") == f"CopyOf={str(to_copy.get_conllu_field('id'))}" for node in sentence):
                return

            cc_tok, cc_rel = converter.cc_assignments[conj]

            copy_node, nodes_copied, last_copy_id = create_new_node(sentence, to_copy, nodes_copied, last_copy_id)
            copy_node.add_edge(Label("conj", eud=get_eud_info(cc_rel, converter)), to_copy)

            # replace cc('gov', 'cc') with cc('to_copy', 'cc')
            # NOTE: this is not mentioned in THE PAPER, but is done in SC (and makes sense).
            if cc_tok:
                cc_tok.replace_edge(Label("cc"), Label("cc"), gov, to_copy)

            for rel in cur_match.edge(cur_match.token('gov'), cur_match.token('to_copy')):
                # replace conj('gov', 'conj') with e.g nmod(copy_node, 'conj')
                conj.remove_all_edges()
                conj.add_edge(Label(rel), copy_node)

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

    def eudpp_expand_prep_conjunctions(sentence, matches, converter):
        nodes_copied = 0
        last_copy_id = -1
        for cur_match in matches:
            to_copy = sentence[cur_match.token('to_copy')]
            conj = sentence[cur_match.token('conj')]
            modifier = sentence[cur_match.token('modifier')]
            already_copied = cur_match.token('already_copied')

            if conj not in converter.cc_assignments:
                continue

            # Check if we already copied this node in this same match (as it is hard to restrict that).
            if already_copied != -1 and \
                    any(node.get_conllu_field("misc") == f"CopyOf={str(to_copy.get_conllu_field('id'))}" for node in sentence):
                return

            copy_node, nodes_copied, last_copy_id = create_new_node(sentence, to_copy, nodes_copied, last_copy_id)
            copy_node.add_edge(Label("conj", eud=get_eud_info(converter.cc_assignments[conj][1], converter)), to_copy)

            # copy relation from modifier to new node e.g nmod:from(copy_node, 'modifier')
            for rel in cur_match.edge(cur_match.token('modifier'), cur_match.token('to_copy')):
                modifier.add_edge(Label(rel, eud=get_eud_info(conj.get_conllu_field('form'), converter)), copy_node)

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

    def extra_fix_nmod_npmod(sentence, matches, converter):
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

    def extra_hyphen_reconstruction(sentence, matches, converter):
        for cur_match in matches:
            subj = cur_match.token("subj")
            verb = cur_match.token("verb")
            noun = cur_match.token("noun")
            sentence[subj].add_edge(Label("nsubj", src="compound", src_type="HYPHEN"), sentence[verb])
            sentence[noun].add_edge(Label(udv("nmod"), src="compound", src_type="HYPHEN"), sentence[verb])

    # The bottle was broken by me.
    extra_passive_alteration_constraint = Full(
        tokens=[
            Token(id="predicate"),
            # the no-object lookup will prevent repeatedly converting this conversion
            Token(id="subjpass", incoming_edges=[HasNoLabel(obj) for obj in obj_options]),
            Token(id="agent", optional=True, spec=[Field(FieldNames.TAG, noun_pos + pron_pos)]),
            Token(id="by", optional=True, spec=[Field(FieldNames.WORD, ["by"])]),  # TODO - english specific
            Token(id="predicates_obj", optional=True)],
        edges=[
            Edge(child="subjpass", parent="predicate", label=[HasLabelFromList([udv("nsubjpass"), udv("csubjpass")])]),
            # TODO: maybe nmod:agent is redundant as we always look at the basic label and agent is part of EUD (afaik)
            Edge(child="agent", parent="predicate", label=[HasLabelFromList([udv("nmod"), udv("nmod:agent")])]),
            Edge(child="by", parent="agent", label=[HasLabelFromList(["case"])]),
            Edge(child="predicates_obj", parent="predicate", label=[HasLabelFromList(obj_options)]),
        ]
    )

    def extra_passive_alteration(sentence, matches, converter):
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
            subj_new_rel = udv("dobj") if predicates_obj == -1 else "iobj"

            # reverse the passivised subject
            subj.add_edge(Label(subj_new_rel, src="passive"), predicate)

    conversion_list = [
        Conversion(ConvTypes.EUD, eud_correct_subj_pass_constraint, eud_correct_subj_pass),
        Conversion(ConvTypes.EUDPP, eudpp_process_simple_2wp_constraint, eudpp_process_simple_2wp),
        Conversion(ConvTypes.EUDPP, eudpp_process_complex_2wp_constraint, eudpp_process_complex_2wp),
        Conversion(ConvTypes.EUDPP, eudpp_process_3wp_constraint, eudpp_process_3wp),
        Conversion(ConvTypes.EUDPP, eudpp_demote_quantificational_modifiers_3w_constraint, eudpp_demote_quantificational_modifiers_3w),
        Conversion(ConvTypes.EUDPP, eudpp_demote_quantificational_modifiers_2w_constraint, eudpp_demote_quantificational_modifiers_2w),
        Conversion(ConvTypes.EUDPP, eudpp_demote_quantificational_modifiers_det_constraint, eudpp_demote_quantificational_modifiers_det),
        Conversion(ConvTypes.BART, extra_nmod_advmod_reconstruction_constraint, extra_nmod_advmod_reconstruction),
        Conversion(ConvTypes.BART, extra_copula_reconstruction_constraint, extra_copula_reconstruction),
        Conversion(ConvTypes.BART, extra_evidential_xcomp_reconstruction_constraint, extra_evidential_xcomp_reconstruction),
        Conversion(ConvTypes.BART, extra_evidential_basic_reconstruction_constraint, extra_evidential_basic_reconstruction),
        Conversion(ConvTypes.BART, extra_aspectual_reconstruction_constraint, extra_aspectual_reconstruction),
        Conversion(ConvTypes.BART, extra_reported_evidentiality_constraint, extra_reported_evidentiality)] + \
        ([Conversion(ConvTypes.BART, extra_fix_nmod_npmod_constraint, extra_fix_nmod_npmod)] if 1 == ud_version else []) + \
        [Conversion(ConvTypes.BART, extra_hyphen_reconstruction_constraint, extra_hyphen_reconstruction),
        Conversion(ConvTypes.EUD, eud_case_sons_of_conjuncts_constraint, eud_case_sons_of_conjuncts),
        Conversion(ConvTypes.EUDPP, eudpp_expand_pp_conjunctions_constraint, eudpp_expand_pp_conjunctions),
        Conversion(ConvTypes.EUDPP, eudpp_expand_prep_conjunctions_constraint, eudpp_expand_prep_conjunctions),
        Conversion(ConvTypes.EUD, eud_heads_of_conjuncts_constraint, eud_heads_of_conjuncts),
        Conversion(ConvTypes.EUD, eud_prep_patterns_constraint, eud_prep_patterns),
        Conversion(ConvTypes.EUD, eud_conj_info_constraint, eud_conj_info),
        Conversion(ConvTypes.EUDPP, eudpp_add_ref_and_collapse_constraint, eudpp_add_ref_and_collapse),
        Conversion(ConvTypes.BART, extra_add_ref_and_collapse_constraint, extra_add_ref_and_collapse),
        Conversion(ConvTypes.EUD, eud_subj_of_conjoined_verbs_constraint, eud_subj_of_conjoined_verbs),
        Conversion(ConvTypes.EUD, extra_xcomp_propagation_constraint, eud_xcomp_propagation),
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


# ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++ #


def remove_funcs(conversions, enhanced, enhanced_plus_plus, enhanced_extra, remove_enhanced_extra_info, remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel):
    if not enhanced:
        conversions = {conversion.name: conversion for conversion in conversions.values() if conversion.conv_type != ConvTypes.EUD}
    if not enhanced_plus_plus:
        conversions = {conversion.name: conversion for conversion in conversions.values() if conversion.conv_type != ConvTypes.EUDPP}
    if not enhanced_extra:
        conversions = {conversion.name: conversion for conversion in conversions.values() if conversion.conv_type != ConvTypes.BART}
    if remove_enhanced_extra_info:
        conversions.pop('eud_conj_info', None)
        conversions.pop('eud_prep_patterns', None)
    if remove_node_adding_conversions:
        # no need to cancel extra_inner_weak_modifier_verb_reconstruction as we have a special treatment there
        conversions.pop('eudpp_expand_prep_conjunctions', None)
        conversions.pop('eudpp_expand_pp_conjunctions', None)
    if remove_unc:
        for func_name in ['extra_dep_propagation', 'extra_compound_propagation', 'extra_conj_propagation_of_poss', 'extra_conj_propagation_of_nmods_forward', 'extra_conj_propagation_of_nmods_backwards', 'extra_advmod_propagation', 'extra_advcl_ambiguous_propagation']:
            conversions.pop(func_name, None)
    if query_mode:
        for func_name in list(conversions.keys()):
            if func_name not in ['extra_nmod_advmod_reconstruction', 'extra_copula_reconstruction', 'extra_evidential_basic_reconstruction', 'extra_evidential_xcomp_reconstruction', 'extra_inner_weak_modifier_verb_reconstruction', 'extra_aspectual_reconstruction', 'eud_correct_subj_pass', 'eud_conj_info', 'eud_prep_patterns', 'eudpp_process_simple_2wp', 'eudpp_process_complex_2wp', 'eudpp_process_3wp', 'eudpp_demote_quantificational_modifiers']:
                conversions.pop(func_name, None)
    if funcs_to_cancel:
        for func_to_cancel in funcs_to_cancel:
            conversions.pop(func_to_cancel, None)

    return conversions


class Convert:
    def __init__(self, *args):
        self.args = args
        self.iids = dict()
        self.cc_assignments = dict()
        # TODO - use kwargs
        self.remove_enhanced_extra_info = args[5]  # should be in the index of remove_enhanced_extra_info param
        self.remove_bart_extra_info = args[6]  # should be in the index of remove_bart_extra_info param

    def __call__(self):
        return self.convert(*self.args)

    def get_rel_set(self, converted_sentence):
        return set([(str(head.get_conllu_field("id")),
                     rel.to_str(self.remove_enhanced_extra_info, self.remove_bart_extra_info),
                     str(tok.get_conllu_field("id"))) for tok in converted_sentence
                    for (head, rels) in tok.get_new_relations() for rel in rels])

    def convert(self, parsed, enhanced, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_enhanced_extra_info,
                remove_bart_extra_info, remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel,
                ud_version=1, one_time_initialized_conversions=None):

        if one_time_initialized_conversions:
            conversions = one_time_initialized_conversions
        else:
            conversions = init_conversions(remove_node_adding_conversions, ud_version)
        conversions = remove_funcs(conversions, enhanced, enhanced_plus_plus, enhanced_extra,
                                   remove_enhanced_extra_info,
                                   remove_node_adding_conversions, remove_unc, query_mode, funcs_to_cancel)

        i = 0
        updated = []
        for sentence in parsed:
            sentence_as_list = [t for t in sentence if t.get_conllu_field("id").major != 0]
            assign_ccs_to_conjs(sentence_as_list, self.cc_assignments)
            i = max(i, self.convert_sentence(sentence_as_list, conversions, conv_iterations))
            updated.append(sentence_as_list)

        return updated, i

    def convert_sentence(self, sentence: Sequence[Token], conversions, conv_iterations: int):
        last_converted_sentence = None
        i = 0
        on_last_iter = ["extra_amod_propagation"]
        do_last_iter = []
        # we iterate till convergence or till user defined maximum is reached - the first to come.
        matcher = Matcher([NamedConstraint(conversion_name, conversion.constraint)
                           for conversion_name, conversion in conversions.items()])
        while i < conv_iterations:
            last_converted_sentence = self.get_rel_set(sentence)
            m = matcher(sentence)
            for conv_name in m.names():
                if conv_name in on_last_iter:
                    do_last_iter.append(conv_name)
                    continue
                matches = m.matches_for(conv_name)
                conversions[conv_name].transformation(sentence, matches, self)
            if self.get_rel_set(sentence) == last_converted_sentence:
                break
            i += 1

        for conv_name in do_last_iter:
            m = matcher(sentence)
            matches = m.matches_for(conv_name)
            conversions[conv_name].transformation(sentence, matches, self)
            if self.get_rel_set(sentence) != last_converted_sentence:
                i += 1

        return i
