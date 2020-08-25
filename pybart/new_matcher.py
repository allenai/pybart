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
# TODO - maybe move this function as a method of the Label constraint? will simplify this code to
#   "for constraint in label_constraints: if not label_constraint.satisfied(actual_labels): return False; return True"
def are_labels_satisfied(label_constraints: Sequence[Label], actual_labels: List[str]) -> bool:
    for constraint in label_constraints:
        if isinstance(constraint, HasNoLabel):
            is_regex = constraint.value.startswith('/') and constraint.value.endswith('/')
            for actual_label in actual_labels:
                if (is_regex and re.match(constraint.value[1:-1], actual_label)) or (constraint.value == actual_label):
                    return False
        elif isinstance(constraint, HasLabelFromList):
            found = False
            for value_option in constraint.value:
                is_regex = value_option.startswith('/') and value_option.endswith('/')
                for actual_label in actual_labels:
                    if (is_regex and re.match(value_option[1:-1], actual_label)) or (value_option == actual_label):
                        found = True
                        break
                if found:
                    break
            if not found:
                return False
    
    return True


class SentenceMatch():
    def __init__(self, name2index):
        self.name2index = name2index
        #self.indices2label = indices2label
    
    def token(self, name: str) -> int:
        return self.name2index.get(name, default=-1)  # TODO - maybe raise instead of returning -1? it means typo in coding
    
    def edge(self, t1: int, t2: int) -> Set[str]:
        # TODO - I really think this would be problematic, because
        raise NotImplemented
        # return self.indices2label.get(t1, default=dict()).get(t2, default=None)  # TODO - is it legitimate to return None here?


class GlobalMatcher:
    def __init__(self, constraint: Full):
        self.constraint = constraint
        self.dont_capture_names = [token.id for token in constraint.tokens if not token.capture]
    
    def _filter(self, match: Mapping[str, int], sentence) -> bool:
        for distance in self.constraint.distances:
            calculated_distance = sentence.index(match[distance.token2]) - sentence.index(match[distance.token1]) - 1
            # TODO - maybe move the following switch case into a method of the Distance constraint? will simplify this code to
            #   "if not distance.satisfied(calculated_distance): return False"
            if isinstance(distance, ExactDistance) and distance.distance != calculated_distance:
                return False
            elif isinstance(distance, UptoDistance) and distance.distance < calculated_distance:
                return False
            else:
                raise ValueError("Unknown Distance type")  # TODO - change to our exception?
        
        for concat in self.constraint.concats:
            # TODO -
            #   1. again, maybe should be moved to constraint's logic
            #   2. can it be partially moved to initialization time (optimization)?
            if isinstance(concat, TokenPair):
                word_indices = [match[concat.token1], match[concat.token2]]
            elif isinstance(concat, TokenTriplet):
                word_indices = [match[concat.token1], match[concat.token2], match[concat.token3]]
            else:
                raise ValueError("Unknown TokenTuple type")  # TODO - change to our exception?
            if "_".join(sentence.get_text(w) for w in word_indices) not in concat.tuple_set:
                return False
        
        for edge in self.constraint.edges:
            if not are_labels_satisfied(edge.label, sentence.get_labels(child=edge.child, parent=edge.parent)):
                return False
        
        return False
    
    def apply(self, matches, sentence) -> List[SentenceMatch]:
        sentence_matches = []
        # form a cartesian product of the match groups
        match_names, matches_indices = zip(*matches.items())
        for match_indices in itertools.product(*matches_indices):
            match_dict = dict(zip(match_names, match_indices))
            if self._filter(match_dict, sentence):
                # keep only captures (who to save)
                _ = [match_dict.pop(name) for name in self.dont_capture_names]
                sentence_matches.append(SentenceMatch(match_dict))
        
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
        self.incoming_constraints = {constraint.id: constraint.incoming_edges for constraint in constraints}
        self.outgoing_constraints = {constraint.id: constraint.outgoing_edges for constraint in constraints}
        self.required_tokens = set()
        self.matcher = SpacyMatcher(self.nlp.vocab)
        # convert the constraint to a list of matchable token patterns
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
                                    are_labels_satisfied(self.incoming_constraints[name], sentence.get_labels(child=token)) and
                                    are_labels_satisfied(self.outgoing_constraints[name], sentence.get_labels(parent=token))]
        return checked_tokens
    
    def apply(self, sentence) -> Mapping[str, List[int]]:  # TODO - define the Graph class we will work with as sentence
        matched_tokens = defaultdict(list)
        matches = self.matcher(sentence.doc)
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

    def __call__(self, sentence) -> Match:  # TODO - define the Graph class we will work with as sentence
        return Match(self.matchers, sentence)
