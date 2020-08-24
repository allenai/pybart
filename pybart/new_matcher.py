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
import spacy
from spacy.matcher import Matcher as SpacyMatcher

from .constraints import *

nlp = spacy.load("en_ud_model_lg")


class SentenceMatch():
    def __init__(self, name2index, indices2label):
        self.name2index = name2index
        self.indices2label = indices2label
    
    def token(self, name: str) -> int:
        return self.name2index[name] if name in self.name2index else -1  # TODO - maybe this is should raise? it means typo in coding
    
    def edge(self, t1: int, t2: int) -> Set[str]:
        return self.indices2label[t1][t2] if t1 in self.indices2label and t2 in self.indices2label[t1] else None  # TODO - is this legitimate?


class GlobalMatcher:
    def __init__(self, constraint: Full):
        raise NotImplemented
    
    def _filter(self, match: Mapping[str, int], sentence) -> bool:
        raise NotImplemented
    
    def apply(self, matches, sentence) -> List[SentenceMatch]:
        sentence_matches = []
        # form a cartesian product of the match groups
        matches_names, matches_indices = zip(*matches.items())
        for bundle in itertools.product(*matches_indices):
            matches_product = dict(zip(matches_names, bundle))
            if self._filter(matches_product, sentence):
                sentence_matches.append(SentenceMatch(matches_product, ))
        
        # TODO - keep only captures (who to save)
        
        return sentence_matches


class TokenMatcher:
    def _convert_to_matchable(self, constraint: Sequence[Token]) -> Sequence[Tuple[str, bool, Any]]:  # TODO - change Any to whatever type we need
        # convert the constraint to a spacy pattern
        raise NotImplemented
    
    def __init__(self, constraints: Sequence[Token]):
        self.required_tokens = set()
        self.matcher = SpacyMatcher(nlp.vocab)
        # convert the constraint to a list of matchable token patterns
        for token_name, is_required, matchable_pattern in self._convert_to_matchable(constraints):
            # add it to the matchable list
            self.matcher.add(token_name, None, matchable_pattern)
            if is_required:
                self.required_tokens.add(token_name)
    
    def _post_spacy_matcher(self, matched_tokens: Mapping[str, List[int]]) -> Mapping[str, List[int]]:
        # handles incoming and outgoing label constraints (still in token level)
        raise NotImplemented
    
    def apply(self, sentence) -> Mapping[str, List[int]]:  # TODO - define the Graph class we will work with as sentence
        matched_tokens = defaultdict(list)
        matches = self.matcher(sentence.doc)
        for match_id, start, end in matches:
            token_name = nlp.vocab.strings[match_id]
            # assert that we matched no more than single token
            if end - 1 == start:
                raise ValueError("matched more than single token")  # TODO - change to our Exception for handling more gently
            token = sentence.doc[start]
            matched_tokens[token_name].append(token.id)
        
        # reverse validate the 'optional' constraint
        if len(self.required_tokens.difference(set(matched_tokens.keys()))) != 0:
            raise ValueError("required token not matched")  # TODO - change to our Exception for handling more gently
        
        # extra token matching out of spacy's scope
        matched_tokens = self._post_spacy_matcher(matched_tokens)
        
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

        # for each concat store the single words of the concat with thier corresepondandt token for token level WORD constraint
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
            incoming_edges = list(token.incoming_edges) + (ins[token.id] if token.id in ins else [])
            outgoing_edges = list(token.outgoing_edges) + (ins[token.id] if token.id in outs else [])
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
