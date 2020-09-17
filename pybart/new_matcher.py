# TODO - define the Graph class we will work with as sentence
# usage example:
# conversions = [SomeConversion, SomeConversion1, ...]
# matcher = Matcher(NamedConstraint(conversion.get_name(), conversion.get_constraint()) for conversion in conversions)
#
# def convert_sentence(sentence, matcher) -> sentence:
#     while … # till convergence of the sentence
#         m = matcher(doc)
#         for conv_name in m.names():
#             matches = m.matches_for(conv_name)
#             transform(matches…) # TBD
#         sentence = ...
#
# for doc in docs:
#     convert_sentence(sentence, matcher)

from dataclasses import replace
from collections import defaultdict
from typing import NamedTuple, Sequence, Mapping, Any, List, Tuple, Generator, Dict, Optional
from spacy.vocab import Vocab
from spacy.matcher import Matcher as SpacyMatcher
from .constraints import *


# function that checks that a sequence of Label constraints is satisfied
def get_matched_labels(label_constraints: Sequence[Label], actual_labels: List[str]) -> Optional[Set[str]]:
    successfully_matched = set()
    # we need to satisfy all constraints in the sequence, so if one fails, return None
    # TODO - optional optimization step:
    #   _ = [successfully_matched.update(constraint.satisfied(actual_labels)) for constraint in label_constraints]
    for constraint in label_constraints:
        satisfied_labels = constraint.satisfied(actual_labels)
        if satisfied_labels is None:
            return None
        successfully_matched.update(satisfied_labels)
    return successfully_matched


class MatchingResult:
    def __init__(self, name2index: Mapping[str, int], indices2label: Mapping[Tuple[int, int], Set[str]]):
        self.name2index = name2index
        self.indices2label = indices2label
    
    # return the index of the specific matched token in the sentence according to its name
    def token(self, name: str) -> int:
        # since optional tokens can have no match, thus should be legitimate to get here their names
        # so we return -1 to inform this
        return self.name2index.get(name, -1)
    
    # return the set of captured labels between the two tokens, given their indices
    def edge(self, t1: int, t2: int) -> Set[str]:
        return self.indices2label.get((t1, t2), None)


class GlobalMatcher:
    def __init__(self, constraint: Full):
        self.constraint = constraint
        self.captured_labels = defaultdict(set)
        # list of token ids that don't require a capture
        self.dont_capture_names = [token.id for token in constraint.tokens if not token.capture]
    
    # filter a single match group according to distance constraints
    def _filter_distance_constraints(self, match: Mapping[str, int]) -> bool:
        # check that the distance between the tokens is not more than or exactly as required
        for distance in self.constraint.distances:
            # Note - we assume that if a token is not in the match dict, then it was an optional one,
            #   and thus we can skip on this distance constraint
            if distance.token1 not in match or distance.token2 not in match:
                continue
            # TODO - why would we need sentence.index
            calculated_distance = match[distance.token2] - match[distance.token1] - 1
            if not distance.satisfied(calculated_distance):
                return False
        return True

    # filter a single match group according to concat constraints
    def _filter_concat_constraints(self, match: Mapping[str, int], sentence) -> bool:
        # check for a two-word or three-word phrase match in a given phrases list
        for concat in self.constraint.concats:
            token_names = concat.get_token_names()
            # Note - we assume that if a token is not in the match dict, then it was an optional one,
            #   and thus we can skip on this concat constraint
            if len(set(concat.get_token_names()).difference(match)) > 0:
                continue
            word_indices = [match[token_name] for token_name in token_names]
            if not concat.satisfied("_".join(sentence.get_text(w) for w in word_indices)):
                return False
        return True

    @staticmethod
    def _try_merge(base_assignment: Mapping[str, int], new_assignment: Mapping[str, int]) -> Mapping[str, int]:
        # try to merge two assignment if they do not contradict
        for k, v in new_assignment.items():
            if v != base_assignment.get(k, v):
                return {}
        return {**base_assignment, **new_assignment}

    def _filter_edge_constraints(self, matches: Mapping[str, List[int]], sentence) -> List[List[Dict[str, int]]]:
        edges_assignments = list()
        # pick possible assignments according to the edge constraint
        for edge in self.constraint.edges:
            edge_assignments = []
            # try each pair as a candidate
            # Note - we assume that if a token is not in the matches dict, then it was an optional one,
            #   and thus we can skip on this edge constraint
            # Note2 - we assume that if a node is not mentioned in any edge constraint,
            #   then it is a redundant token-constraint (TODO - validate this assumption)
            for child in matches.get(edge.child, []):
                for parent in matches.get(edge.parent, []):
                    # check if edge constraint is satisfied
                    captured_labels = \
                        get_matched_labels(edge.label, sentence.get_labels(child=child, parent=parent))
                    if captured_labels is None:
                        continue
                    # TODO - compare the speed of non-edge filtering here to the current post-merging location:
                    #   "if self._filter(assignment, sentence)"
                    # store all captured labels according to the child-parent token pair
                    self.captured_labels[(edge.child, child, edge.parent, parent)].update(captured_labels)
                    # keep the filtered assignment for further merging
                    edge_assignments.append({edge.child: child, edge.parent: parent})
            if edge_assignments:
                edges_assignments.append(edge_assignments)
        return edges_assignments

    @staticmethod
    def _merge_edges_assignments(edges_assignments: List[List[Dict[str, int]]]) -> List[Dict[str, int]]:
        merges = []
        # for each list of possible assignments of an edge
        for edge_assignments in edges_assignments:
            new_merges = []
            # for each merged assignment. (we need an empty dictionary for the first cycle to start with)
            for merged in (merges if merges else [{}]):
                # for each possible assignment in the current list
                for assignment in edge_assignments:
                    # try to merge (see that there is no contradiction on hashing)
                    just_merged = GlobalMatcher._try_merge(merged, assignment)
                    if just_merged:
                        new_merges.append(just_merged)
            if not new_merges:
                return []
            merges = new_merges

        return merges

    def apply(self, matches: Mapping[str, List[int]], sentence) -> Generator[MatchingResult, None, None]:
        filtered = self._filter_edge_constraints(matches, sentence)
        merges = self._merge_edges_assignments(filtered)

        for merged_assignment in merges:
            # TODO - compare the speed of non-edge filtering here to the on-going edge filter (see previous todo)
            if self._filter_distance_constraints(merged_assignment) and \
                    self._filter_concat_constraints(merged_assignment, sentence):
                # keep only required captures
                _ = [merged_assignment.pop(name, None) for name in self.dont_capture_names]
                captured_labels = {(v1, v2): labels for (k1, v1, k2, v2), labels in self.captured_labels.items()
                                   if merged_assignment[k1] == v1 and merged_assignment[k2] == v2}
                # append assignment to output
                yield MatchingResult(merged_assignment, captured_labels)


class TokenMatcher:
    def __init__(self, constraints: Sequence[Token], vocab: Vocab):
        self.vocab = vocab
        self.matcher = SpacyMatcher(vocab)
        # store the no_children/incoming/outgoing token constraints according to the token id for post spacy matching
        self.no_children = {constraint.id: constraint.no_children for constraint in constraints}
        self.incoming_constraints = {constraint.id: constraint.incoming_edges for constraint in constraints}
        self.outgoing_constraints = {constraint.id: constraint.outgoing_edges for constraint in constraints}
        
        # convert the constraint to a list of matchable token patterns
        self.required_tokens = set()
        for token_name, is_required, matchable_pattern in self._make_patterns(constraints):
            # add it to the matchable list
            self.matcher.add(token_name, None, [matchable_pattern])
            if is_required:
                self.required_tokens.add(token_name)
    
    # convert the constraint to a spacy pattern
    @staticmethod
    def _make_patterns(constraints: Sequence[Token]) -> List[Tuple[str, bool, Dict[str, Dict[str, Sequence[str]]]]]:
        patterns = []
        for constraint in constraints:
            pattern = dict()
            for spec in constraint.spec:
                # TODO - the list is comprised of either strings or regexes - so spacy's 'IN' or 'REGEX' won't do
                #   for now, assuming a list is given (hence the use of "IN"/"NOT_IN")
                in_or_not_in = "IN" if spec.in_sequence else "NOT_IN"
                if spec.field == FieldNames.WORD:
                    # TODO - check if you need non LOWER case (i.e. TEXT)
                    pattern["LOWER"] = {in_or_not_in: spec.value}
                elif spec.field == FieldNames.LEMMA:
                    pattern["LEMMA"] = {in_or_not_in: spec.value}
                elif spec.field == FieldNames.TAG:
                    pattern["TAG"] = {in_or_not_in: spec.value}
                elif spec.field == FieldNames.ENTITY:
                    pattern["ENT_TYPE"] = {in_or_not_in: spec.value}
            
            patterns.append((constraint.id, not constraint.optional, pattern))
        return patterns
    
    def _post_spacy_matcher(self, matched_tokens: Mapping[str, List[int]], sentence) -> Mapping[str, List[int]]:
        # handles incoming and outgoing label constraints (still in token level)
        checked_tokens = defaultdict(list)
        for name, token_indices in matched_tokens.items():
            for token in token_indices:
                if self.no_children[name] and (len(sentence.get_labels(parent=token)) != 0):
                    continue
                out_matched = get_matched_labels(self.outgoing_constraints[name], sentence.get_labels(parent=token))
                in_matched = get_matched_labels(self.incoming_constraints[name], sentence.get_labels(child=token))
                if in_matched is None or out_matched is None:
                    # TODO - consider adding a 'token in self.required_tokens' validation here for optimization
                    continue
                checked_tokens[name].append(token)
        return checked_tokens
    
    def apply(self, sentence) -> Optional[Mapping[str, List[int]]]:
        matched_tokens = defaultdict(list)
        
        # apply spacy's token-level match
        matches = self.matcher(sentence.doc())
        # validate the span and store each matched token
        for match_id, start, end in matches:
            token_name = self.vocab.strings[match_id]
            # assert that we matched no more than single token
            if end - 1 != start:
                continue
            token = sentence.doc()[start]
            matched_tokens[token_name].append(token.i)

        # extra token matching out of spacy's scope
        matched_tokens = self._post_spacy_matcher(matched_tokens, sentence)

        # reverse validate the 'optional' constraint
        if len(self.required_tokens.difference(set(matched_tokens.keys()))) != 0:
            return None
        
        return matched_tokens


class Match:
    def __init__(self, token_matchers: Mapping[str, TokenMatcher],
                 global_matchers: Mapping[str, GlobalMatcher], sentence):
        assert token_matchers.keys() == global_matchers.keys()
        self.token_matchers = token_matchers
        self.global_matchers = global_matchers
        self.sentence = sentence
    
    def names(self) -> List[str]:
        # return constraint-name list
        return list(self.token_matchers.keys())
    
    def matches_for(self, name: str) -> Generator[MatchingResult, None, None]:
        # token match
        matches = self.token_matchers[name].apply(self.sentence)
        if matches is None:
            return
        
        # filter
        yield from self.global_matchers[name].apply(matches, self.sentence)


class NamedConstraint(NamedTuple):
    name: str
    constraint: Full


# add TokenConstraints based on the other non-token constraints (optimization step).
def preprocess_constraint(constraint: Full) -> Full:
    # for each edge store the labels that could be filtered as incoming or outgoing token constraints
    #   in the parent or child accordingly
    outs = defaultdict(list)
    ins = defaultdict(list)
    for edge in constraint.edges:
        # skip HasNoLabel as they check for non existing label between two nodes,
        #   and if we add a token constraint it would be to harsh
        if isinstance(edge.label, HasNoLabel):
            continue
        outs[edge.parent].extend(list(edge.label))
        ins[edge.child].extend(list(edge.label))

    # for each concat store the single words of the concat
    #   with their correspondent token for token level WORD constraint
    words = defaultdict(set)
    for concat in constraint.concats:
        zipped_concat = list(zip(*[tuple(t.split("_")) for t in concat.tuple_set]))
        if isinstance(concat, TokenPair) or isinstance(concat, TokenTriplet):
            words[concat.token1].update(set(zipped_concat[0]))
            words[concat.token2].update(set(zipped_concat[1]))
        if isinstance(concat, TokenTriplet):
            words[concat.token3].update(set(zipped_concat[2]))

    # rebuild the constraint (as it is immutable)
    tokens = []
    for token in constraint.tokens:
        incoming_edges = list(token.incoming_edges) + ins.get(token.id, [])
        outgoing_edges = (list(token.outgoing_edges) + outs.get(token.id, [])) if not token.no_children else []
        # add the word constraint to an existing WORD field if exists
        word_fields = [replace(s, value=list(words.get(token.id, set()).union(s.value)))
                       for s in token.spec if s.field == FieldNames.WORD]
        if (len(word_fields) == 0) and (token.id in words):
            # simply create a new WORD field
            word_fields = [Field(FieldNames.WORD, list(words[token.id]))]
        # attach the replaced/newly-formed word constraint to the rest of the token spec
        spec = [s for s in token.spec if s.field != FieldNames.WORD] + word_fields
        tokens.append(replace(token, spec=spec, incoming_edges=incoming_edges, outgoing_edges=outgoing_edges))
    return replace(constraint, tokens=tokens)


class Matcher:
    def __init__(self, constraints: Sequence[NamedConstraint], vocab: Vocab):
        self.token_matchers = dict()
        self.global_matchers = dict()
        for constraint in constraints:
            # preprocess the constraints (optimizations)
            preprocessed_constraint = preprocess_constraint(constraint.constraint)
            
            # initialize internal matchers
            self.token_matchers[constraint.name] = TokenMatcher(preprocessed_constraint.tokens, vocab)
            self.global_matchers[constraint.name] = GlobalMatcher(preprocessed_constraint)
    
    # apply the matching process on a given sentence
    def __call__(self, sentence) -> Match:
        return Match(self.token_matchers, self.global_matchers, sentence)
