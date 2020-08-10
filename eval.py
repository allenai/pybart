from dataclasses import dataclass
from itertools import islice
from typing import List, Tuple, Iterator
from tqdm import tqdm

from spike.datamodel.dataset import FileBasedDataSet
from spike.evaluation.match import RetrievalRelevanceStats, compute_match
from spike.utils.iteration import count_iterable, interweave_sorted_with_override

from spike.pattern_generation.compilation.spike_compiler import SpikeRuleSet
from spike.rest.definitions import Relation
from spike.match.matchers import IndexedSpikeMatcher
from spike.match.transformations import BinaryRelationTransformer
from spike.match.common import Matcher
from spike.datamodel.definitions import Extraction, Document, Sentence
from spike.pattern_generation.compilation import spike_compiler

PatternName = str
TotalExtractions = int


@dataclass(frozen=True)
class EvalResults:
    global_stats: RetrievalRelevanceStats

    # list[Tuple] instead of dict because we allow identical keys
    stats_per_pattern: List[Tuple[PatternName, RetrievalRelevanceStats, TotalExtractions]]

    def get_global_stats(self):
        """Lazy method to communicate with the UI API, (to avoid full json encoding/decoding)"""
        return get_stats_as_dict(self.global_stats)

    def get_stats_per_pattern(self):
        """Lazy method to communicate with thethe UI API (to avoid full json encoding/decoding)"""
        return [
            (pattern, get_stats_as_dict(pattern_stats), total_extractions)
            for (pattern, pattern_stats, total_extractions) in self.stats_per_pattern
        ]


def my_prec(reles, rets):
    return (len(reles.intersection(rets)) / len(rets)) if len(rets) > 0 else 0.0


def my_recall(reles, rets):
    return (len(reles.intersection(rets)) / len(reles)) if len(reles) > 0 else 0.0


def my_f1(reles, rets):
    prec = my_prec(reles, rets)
    recall = my_recall(reles, rets)
    return ((2 * prec * recall) / (prec + recall)) if (prec + recall) > 0 else 0.0


def evaluate_relation(data_set: FileBasedDataSet, spike_rule_set: SpikeRuleSet, relation: Relation, in_port: str, in_port2: str, compute_global: bool = True, compute_per_pattern: bool = False) -> EvalResults:
    matcher = IndexedSpikeMatcher(data_set, odinson_wrapper_url=in_port, odin_wrapper_url=in_port2).transform(BinaryRelationTransformer(relation))

    global_eval_stats = []
    if compute_global:
        global_eval_stats, _, _ = stats_for_relation(matcher, data_set, spike_rule_set, relation)

    labels = dict()
    stats_per_pattern = []
    if compute_per_pattern:
        for rule in spike_rule_set:
            single_rule_rule_set = [rule]
            single_rule_stats, reles, rets = stats_for_relation(matcher, data_set, single_rule_rule_set, relation)
            #total_extractions = count_iterable(matcher.match(single_rule_rule_set))
            label = rule.original_text if rule.original_text is not None else str(rule)
            cur_f1 = EvalResults(single_rule_stats, None).get_global_stats()['f1']
            stats_per_pattern.append((cur_f1 if (cur_f1 != float("inf")) else 0.0, label, single_rule_stats, reles, rets))
        sorted_stats = sorted(stats_per_pattern, reverse=True)
        total_reles = set()
        total_rets = set()
        for stat in sorted_stats:
            if my_f1(total_reles, total_rets) < my_f1(total_reles.union(stat[3]), total_rets.union(stat[4])):
                total_reles = total_reles.union(stat[3])
                #labels.append(stat[1])
                labels[stat[1]] = len(stat[4].difference(total_rets).intersection(total_reles))
                total_rets = total_rets.union(stat[4])

        #summed_f1 = my_f1(total_reles, total_rets)
        #computed_stats, _, _ = stats_for_relation(matcher, data_set, spike_compiler.from_text("\n".join(labels), relation)[0], relation)
        #computed_f1 = EvalResults(computed_stats, None).get_global_stats()['f1']
        #print("dev_tuned(identfy by_port: %s) pattern list summed f1 VS computed f1: %.4f VS %.4f" % (in_port.split(":")[-1], summed_f1, computed_f1))
        #with open("dev_tuned_by_port_%s.log" % in_port.split(":")[-1], "w") as f:
        #    f.write("dev_tuned pattern list summed f1 VS computed f1: %.4f VS %.4f,\n\tAnd summed prec: %.4f and recall: %.4f for fun" % \
        #        (summed_f1, computed_f1, my_prec(total_reles, total_rets), my_recall(total_reles, total_rets)))
        global_eval_stats = RetrievalRelevanceStats(
            relevant=len(total_reles),
            retrieved=len(total_rets),
            retrieved_and_relevant=len(total_reles.intersection(total_rets)))

    return EvalResults(global_eval_stats, stats_per_pattern), labels


def get_stats_as_dict(stats: RetrievalRelevanceStats):
    return {
        "relevant": stats.relevant,
        "retrieved": stats.retrieved,
        "retrievedAndRelevant": stats.retrieved_and_relevant,
        "precision": stats.precision,
        "recall": stats.recall,
        "f1": stats.f1,
    }


def _to_empty_extractions(it: Iterator[Tuple[Document, Sentence]]) -> Iterator[Extraction]:
    return map(lambda p: Extraction.empty(*p), it)


def stats_for_relation(
    matcher: Matcher[FileBasedDataSet, SpikeRuleSet, Extraction, int],
    data_set: FileBasedDataSet,
    spike_rule_set: SpikeRuleSet,
    relation: Relation,
    limit: int = None,
) -> RetrievalRelevanceStats:
    """
    Get the total match statistics over an entire data set per requested relation.
    If limit X is provided, the statistics is only collected on the first X sentences.

    Args:
        matcher: a matcher from spike rule set to extraction
        data_set: the data set on which we are evaluating on
        spike_rule_set: a spike rule set to evaluate
        relation: the relation to evaluate
        limit: an optional limit, to collect statistics only part of the data set

    Returns: match statistics for the given relation

    """
    result = RetrievalRelevanceStats.zero()

    def extractions_comp(e1: Extraction, e2: Extraction) -> int:
        return data_set.absolute_index(e2.sent.source) - data_set.absolute_index(e1.sent.source)

    extractions_iter = interweave_sorted_with_override(
        matcher.match(spike_rule_set),
        _to_empty_extractions(data_set.sentences_with_relation(relation.id)),
        extractions_comp,
    )

    if limit:
        extractions_iter = islice(extractions_iter, limit)

    extractions = list(extractions_iter)
    rets = set()
    reles = set()
    for ext in tqdm(extractions, desc="Evaluating sentences", total=len(extractions), disable=True):
        # statistics over different sentences can be safely added up to compute the total
        lens, cur_reles, cur_rets = compute_match(relation.label, ext.sent, ext.sent_extractions)
        reles = reles.union(cur_reles)
        rets = rets.union(cur_rets)
        result += lens

    return result, reles, rets
