# usage example:
# conversions = [SomeConversion, SomeConversion1, ...]
# matcher = Matcher(NamedConstraint(conversion.get_name(), conversion.get_constraint()) for conversion in conversions)
#
# def convert_sentence(sentence, matcher) -> sentence:
#     while … # till convergance of the sentence
#         m = matcher(doc)
#         for conv_name in m.names():
#             matches = m.matches_for(conv_name)
#             transform(matches…) # TBD
#         sentence = ...
#
# for doc in docs:
#     convert_sentence(sentence, matcher)

import itertools
from collections import defaultdict
from typing import NamedTuple, Sequence, Mapping, Any, List, Tuple
import re
import spacy
from spacy.matcher import Matcher as SpacyMatcher
from .constraints import *


# function that checks that a sequence of Label constraints is satisfied
# TODO - maybe move this function as a 'satisfied' method of the Label constraint? will simplify this code to
#   "for constraint in label_constraints: if not label_constraint.satisfied(actual_labels): return False; return True"
def are_labels_satisfied(label_constraints: Sequence[Label], actual_labels: List[str]) -> Tuple[bool, Set[str]]:
    successfully_matched = set()
    # we need to satisfy all constraints in the sequence, so if one fails, return False
    for constraint in label_constraints:
        if isinstance(constraint, HasNoLabel):
            # check if a regex or exact match is required
            is_regex = constraint.value.startswith('/') and constraint.value.endswith('/')
            
            # for each edged label, check if the label matches the constraint, and fail if it does,
            #   because it is a negative search (that is non of the labels should match)
            for actual_label in actual_labels:
                if (is_regex and re.match(constraint.value[1:-1], actual_label)) or (constraint.value == actual_label):
                    return False, set()
        elif isinstance(constraint, HasLabelFromList):
            current_successfully_matched = set()
            # at least one of the constraint strings should match, so return False only if none of them did.
            for value_option in constraint.value:
                # check if a regex or exact match is required
                is_regex = value_option.startswith('/') and value_option.endswith('/')

                # for each edged label, check if the label matches the constraint, and store it if it does,
                #   because it is a positive search (that is at least one label should match)
                for actual_label in actual_labels:
                    if (is_regex and re.match(value_option[1:-1], actual_label)) or (value_option == actual_label):
                        # store the matched label
                        current_successfully_matched.add(actual_label)
            # this means no match, so fail
            if not current_successfully_matched:
                return False, set()
            
            # concat the captured labels of the current constraint with previous ones, as there can be a few positive constraints.
            successfully_matched.update(current_successfully_matched)
    
    return True, successfully_matched


class SentenceMatch:
    def __init__(self, name2index: Mapping[str, int], indices2label: Mapping[Tuple[int, int], Set[str]]):
        self.name2index = name2index
        self.indices2label = indices2label
    
    # return the index of the specific matched token in the sentence according to its name
    def token(self, name: str) -> int:
        return self.name2index.get(name, default=-1)  # TODO - maybe raise instead of returning -1? it means typo in coding
    
    # return the set of captured labels between the two tokens, given their indices
    def edge(self, t1: int, t2: int) -> Set[str]:
        return self.indices2label.get((t1, t2), default=None)  # TODO - is it legitimate to return None here?


class GlobalMatcher:
    def __init__(self, constraint: Full):
        self.constraint = constraint
        self.captured_labels = defaultdict(set)
        # list of token ids that don't require a capture
        self.dont_capture_names = [token.id for token in constraint.tokens if not token.capture]
    
    # filter a single match group according to non-token constraints
    def _filter(self, match: Mapping[str, int], sentence) -> bool:
        # check that the distance between the tokens is not more than or exactly as required
        for distance in self.constraint.distances:
            if distance.token1 not in match or distance.token2 not in match:
                continue
            calculated_distance = sentence.index(match[distance.token2]) - sentence.index(match[distance.token1]) - 1
            # TODO - maybe move the following switch case into a method of the Distance constraint? will simplify this code to
            #   "if not distance.satisfied(calculated_distance): return False"
            if isinstance(distance, ExactDistance) and distance.distance != calculated_distance:
                return False
            elif isinstance(distance, UptoDistance) and distance.distance < calculated_distance:
                return False
            else:
                raise ValueError("Unknown Distance type")  # TODO - change to our exception?
        
        # check for a two-word or three-word phrase match in a given phrases list
        for concat in self.constraint.concats:
            # TODO -
            #   1. again, maybe should be moved to constraint's logic
            #   2. can it be partially moved to initialization time (optimization)?
            if isinstance(concat, TokenPair):
                if concat.token1 not in match or concat.token2 not in match:
                    continue
                word_indices = [match[concat.token1], match[concat.token2]]
            elif isinstance(concat, TokenTriplet):
                if concat.token1 not in match or concat.token2 not in match or concat.token3 not in match:
                    continue
                word_indices = [match[concat.token1], match[concat.token2], match[concat.token3]]
            else:
                raise ValueError("Unknown TokenTuple type")  # TODO - change to our exception?
            if "_".join(sentence.get_text(w) for w in word_indices) not in concat.tuple_set:
                return False
        
        return True
        
    @staticmethod
    def _try_merge(base_assignment: Mapping[str, int], new_assignment: Mapping[str, int]) -> Mapping[str, int]:
        # try to merge two assignment if they do not contradict
        for k, v in new_assignment.items():
            if v != base_assignment.get(k, v):
                return {}
        return {**base_assignment, **new_assignment}
    
    def apply(self, matches: Mapping[str, List[int]], sentence) -> List[SentenceMatch]:
        sentence_matches = []
        edge_assignments = list()
        # pick possible assignments according to the edge constraint
        for i, edge in enumerate(self.constraint.edges):
            edge_assignments[i] = []
            # try each pair as a candidate
            for child in matches[edge.child]:
                for parent in matches[edge.parent]:
                    # check if edge constraint is satisfied
                    is_satisfied, captured_labels = are_labels_satisfied(edge.label, sentence.get_labels(child=child, parent=parent))
                    assignment = {edge.child: child, edge.parent: parent}
                    
                    # TODO - compare the speed of non-edge filtering here to the current post-merging location
                    if is_satisfied:  # and self._filter(assignment, sentence):
                        # store all captured labels according to the child-parent token pair
                        self.captured_labels[(edge.child, child, edge.parent, parent)].update(captured_labels)
                        # keep the filtered assignment for further merging
                        edge_assignments[i].append(assignment)
        
        merges = [{}]
        # for each list of possible assignments of an edge
        for i in range(len(self.constraint.edges)):
            new_merges = []
            # for each merged assignment
            for merged in merges:
                # for each possible assignment in the current list
                for assignment in edge_assignments[i]:
                    # try to merge (see that there is no contradiction on hashing)
                    just_merged = self._try_merge(merged, assignment)
                    if just_merged:
                        new_merges.append(just_merged)
            if not new_merges:
                return []
            merges = new_merges
        
        for merged_assignment in merges:
            # TODO - compare the speed of non-edge filtering here to the on-going edge filter (see previous todo)
            if self._filter(merged_assignment, sentence):
                # keep only required captures
                _ = [merged_assignment.pop(name) for name in self.dont_capture_names]
                captured_labels = {(v1, v2): labels for (k1, v1, k2, v2), labels in self.captured_labels.items()
                                   if merged_assignment[k1] == v1 and merged_assignment[k2] == v2}
                # append assignment to output
                sentence_matches.append(SentenceMatch(merged_assignment, captured_labels))
        return sentence_matches
       

class TokenMatcher:
    # convert the constraint to a spacy pattern
    @staticmethod
    def _convert_to_matchable(constraints: Sequence[Token]) -> List[Tuple[str, bool, Any]]:  # TODO - change Any to whatever type we need
        patterns = []
        for constraint in constraints:
            pattern = dict()
            for spec in constraint.spec:
                # TODO - the list is comprised of either strings or regexes - so spacy's 'IN' or 'REGEX' alone is not enough
                #   (we need a combination or another solution)
                if spec.field == FieldNames.WORD:
                    # TODO - add separation between default LOWER and non default TEXT
                    pattern["TEXT"] = {"IN", spec.value}
                elif spec.field == FieldNames.LEMMA:
                    pattern["LEMMA"] = {"IN", spec.value}
                elif spec.field == FieldNames.TAG:
                    pattern["TAG"] = {"IN", spec.value}
                elif spec.field == FieldNames.ENTITY:
                    pattern["ENT_TYPE"] = {"IN", spec.value}
            
            patterns.append((constraint.id, not constraint.optional, pattern))
        return patterns
    
    def __init__(self, constraints: Sequence[Token]):
        self.nlp = spacy.load("en_ud_model_lg")
        self.matcher = SpacyMatcher(self.nlp.vocab)
        # store the incoming/outgoing token constraints according to the token id for post token-level matching
        self.incoming_constraints = {constraint.id: constraint.incoming_edges for constraint in constraints}
        self.outgoing_constraints = {constraint.id: constraint.outgoing_edges for constraint in constraints}
        
        # convert the constraint to a list of matchable token patterns
        self.required_tokens = set()
        for token_name, is_required, matchable_pattern in self._convert_to_matchable(constraints):
            # add it to the matchable list
            self.matcher.add(token_name, None, matchable_pattern)
            if is_required:
                self.required_tokens.add(token_name)
    
    def _post_spacy_matcher(self, matched_tokens: Mapping[str, List[int]], sentence) -> Mapping[str, List[int]]:
        # handles incoming and outgoing label constraints (still in token level)
        checked_tokens = dict()
        for name, token_indices in matched_tokens.items():
            checked_tokens[name] = [token for token in token_indices if
                                    are_labels_satisfied(self.incoming_constraints[name], sentence.get_labels(child=token))[0] and
                                    are_labels_satisfied(self.outgoing_constraints[name], sentence.get_labels(parent=token))[0]]
        return checked_tokens
    
    def apply(self, sentence) -> Mapping[str, List[int]]:  # TODO - define the Graph class we will work with as sentence
        matched_tokens = defaultdict(list)
        
        # apply spacy's token-level match
        matches = self.matcher(sentence.doc)
        # validate the span and store each matched token
        for match_id, start, end in matches:
            token_name = self.nlp.vocab.strings[match_id]
            # assert that we matched no more than single token
            if end - 1 == start:
                raise ValueError("matched more than single token")  # TODO - change to our Exception for handling more gently
            token = sentence.doc[start]
            matched_tokens[token_name].append(token.id)
        
        # reverse validate the 'optional' constraint
        if len(self.required_tokens.difference(set(matched_tokens.keys()))) != 0:
            raise ValueError("required token not matched")  # TODO - change to our Exception for handling more gently
        
        # extra token matching out of spacy's scope
        matched_tokens = self._post_spacy_matcher(matched_tokens, sentence)
        
        return matched_tokens


class Matchers(NamedTuple):
    token_matcher: TokenMatcher
    global_matcher: GlobalMatcher


class Match:
    def __init__(self, matchers: Mapping[str, Matchers], sentence):  # TODO - define the Graph class we will work with as sentence
        self.matchers = matchers
        self.sentence = sentence
    
    def names(self) -> List[str]:
        # return constraint-name list
        return list(self.matchers.keys())
    
    def matcher_for(self, name: str) -> List[SentenceMatch]:
        # token match
        matches = self.matchers[name].token_matcher.apply(self.sentence)
        
        # filter
        sentence_matches = self.matchers[name].global_matcher.apply(matches, self.sentence)
        
        return sentence_matches


class NamedConstraint(NamedTuple):
    name: str
    constraint: Full


class Matcher:
    @staticmethod
    # add TokenConstraints based on the other non-token constraints (optimization step).
    def _preprocess(constraint: Full) -> Full:
        # for each edge store the labels that could be filtered as incoming or outgoing token constraints in the parent or child accordingly
        outs = defaultdict(list)
        ins = defaultdict(list)
        for edge in constraint.edges:
            # skip HasNoLabel as they check for non existing label between two nodes, and if we add a token constraint it would be to harsh
            if isinstance(edge.label, HasNoLabel):
                continue
            outs[edge.child].extend(list(edge.label))
            ins[edge.parent].extend(list(edge.label))

        # for each concat store the single words of the concat with their correspondent token for token level WORD constraint
        words = defaultdict(list)
        for concat in constraint.concats:
            zipped_concat = list(zip(*[tuple(t.split("_")) for t in concat.tuple_set]))
            if isinstance(concat, TokenPair) or isinstance(concat, TokenTriplet):
                words[concat.token1].append(zipped_concat[0])
                words[concat.token2].append(zipped_concat[1])
            if isinstance(concat, TokenTriplet):
                words[concat.token3].append(zipped_concat[2])
        
        # TODO - this is kinda horrible, find alternatives
        # rebuild the constraint (as it is immutable)
        tokens = []
        for token in constraint.tokens:
            if token.id in words:
                # add the word constraint to an existing WORD field if exists, otherwise simply create a new WORD field
                if any(s.field == FieldNames.WORD for s in token.spec):
                    spec = [Field(s.field, list(s.value) + (words[token.id] if s.field == FieldNames.WORD else [])) for s in token.spec]
                else:
                    spec = list(token.spec) + [Field(FieldNames.WORD, words[token.id])]
            else:
                spec = list(token.spec)
            incoming_edges = list(token.incoming_edges) + ins.get(token.id, default=[])
            outgoing_edges = list(token.outgoing_edges) + outs.get(token.id, default=[])
            tokens.append(Token(id=token.id, capture=token.capture, optional=token.optional, is_root=token.is_root, spec=spec,
                                incoming_edges=incoming_edges, outgoing_edges=outgoing_edges))
        return Full(tokens=tokens, edges=constraint.edges, distances=constraint.distances, concats=constraint.concats)

    def __init__(self, constraints: Sequence[NamedConstraint]):
        self.matchers = dict()
        for constraint in constraints:
            # preprocess the constraints (optimizations)
            preprocessed_constraint = self._preprocess(constraint.constraint)
            
            # initialize internal matchers
            self.matchers[constraint.name] = Matchers(TokenMatcher(preprocessed_constraint.tokens), GlobalMatcher(preprocessed_constraint))

    # apply the matching process on a given sentence
    def __call__(self, sentence) -> Match:  # TODO - define the Graph class we will work with as sentence
        return Match(self.matchers, sentence)
