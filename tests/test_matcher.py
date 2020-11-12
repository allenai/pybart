import math
import pytest
from pybart.spacy_wrapper import parse_spacy_sent
from pybart.matcher import *
import spacy
from pybart import matcher


def stub_get_text(stub_self, i):
    return {0: "test1", 1: "test2", 2: "test3"}[i]


def stub_get_labels(stub_self, child=0, parent=0):
    if child == 1:
        if parent == 2:
            return ["bad_label"]
        else:
            return ["some_label"]
    elif parent == 3 or parent == 2:
        return ["some_label"]
    else:
        return []


@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    keep_get_text = matcher.get_text
    matcher.get_text = stub_get_text
    keep_get_labels = matcher.get_labels
    matcher.get_labels = stub_get_labels

    def remove_test_dir():
        matcher.get_text = keep_get_text
        matcher.get_labels = keep_get_labels
    request.addfinalizer(remove_test_dir)


nlp = spacy.load("en_ud_model_sm")

docs = [
    nlp("He went home today"),
    nlp("test sentence 1"),
    nlp("He wanted to go"),
    nlp("He went home")
]
sentences = [[t for t in parse_spacy_sent(doc) if t.get_conllu_field("id") != 0] for doc in docs]


def init_full_constraints():
    some_constraint1 = Full(
        tokens=[Token("name1"), Token("name2"), Token("name3")],
        edges=[Edge("name1", "name2", [])],
        distances=[ExactDistance("name1", "name2", 0), UptoDistance("name1", "name2", 0)],
        concats=[TokenPair({"bla1_bla2"}, "name1", "name2"),
                 TokenTriplet({"bla1_bla2_bla3"}, "name1", "name2", "name3")])

    some_constraint2 = Full(
        tokens=[Token("name1"), Token("name2"), Token("name3")],
        edges=[Edge("name1", "name2", [])],
        distances=[ExactDistance("name1", "name2", 0), UptoDistance("name1", "name2", 0)],
        concats=[TokenPair({"bla1_bla2"}, "name1", "name2"),
                 TokenTriplet({"bla1_bla2_bla3"}, "name1", "name2", "name3")])

    return [some_constraint1, some_constraint2]


def try_helper(try_code, exception_str, exception):
    try:
        try_code()
        assert False
    except exception as e:
        assert str(e) == exception_str


class TestConstraints:
    def test_has_label_from_list(self):
        label_con = HasLabelFromList(['/nmod.*/', 'nsubj'])
        assert {"nmod", "nmod:of", "nsubj"} == \
               label_con.satisfied(["bla_nmod", "nmod", "nmod:of", "nsubj", "nsubjpass"])
        assert label_con.satisfied(["bla_nmod", "nsubjpass"]) is None

    def test_has_no_label(self):
        no_label_con1 = HasNoLabel('/nmod.*/')
        no_label_con2 = HasNoLabel('nsubj')
        assert no_label_con1.satisfied(["bla_nmod", "nsubj", "nsubjpass"]) == set()
        assert no_label_con2.satisfied(["bla_nmod", "nmod", "nmod:of", "nsubjpass"]) == set()
        assert no_label_con1.satisfied(["bla_nmod", "nmod:of", "nsubj"]) is None
        assert no_label_con2.satisfied(["bla_nmod", "nsubj", "nsubjpass"]) is None

    def test_exact_distance(self):
        dist0 = ExactDistance('tok1', 'tok2', 0)
        dist1 = ExactDistance('tok1', 'tok2', 1)
        assert dist0.satisfied(0) and not dist0.satisfied(1)
        assert dist1.satisfied(1) and not dist1.satisfied(0)
        try_helper(lambda: ExactDistance('tok1', 'tok2', -1), "Exact distance can't be negative", ValueError)
        try_helper(
            lambda: ExactDistance('tok1', 'tok2', math.inf), "Exact distance can't be infinity", ValueError)

    def test_up_to_distance(self):
        dist0 = UptoDistance('tok1', 'tok2', 0)
        dist1 = UptoDistance('tok1', 'tok2', 1)
        dist_inf = UptoDistance('tok1', 'tok2', math.inf)
        assert dist0.satisfied(0) and not dist0.satisfied(1)
        assert dist1.satisfied(0) and dist1.satisfied(1)
        assert dist_inf.satisfied(0) and dist_inf.satisfied(1000) and dist_inf.satisfied(math.inf)
        try_helper(lambda: UptoDistance('tok1', 'tok2', -1), "'up-to' distance can't be negative", ValueError)

    def test_token_tuple(self):
        pair_in = TokenPair({"bla1_bla2"}, "tok1", "tok2", True)
        pair_not_in = TokenPair({"bla1_bla2"}, "tok1", "tok2", False)
        triplet_in = TokenTriplet({"bla1_bla2_bla3"}, "tok1", "tok2", "tok3", True)
        triplet_not_in = TokenTriplet({"bla1_bla2_bla3"}, "tok1", "tok2", "tok3", False)
        words = {"tok1": "bla1", "tok2": "bla2", "tok3": "bla3"}
        flipped_words = {"tok1": "bla2", "tok2": "bla1", "tok3": "bla3"}

        for tok_tuple in [pair_in, pair_not_in, triplet_in, triplet_not_in]:
            assert not (tok_tuple.in_set ^
                        tok_tuple.satisfied("_".join(words[tok] for tok in tok_tuple.get_token_names())))
            assert (tok_tuple.in_set ^
                   tok_tuple.satisfied("_".join(flipped_words[tok] for tok in tok_tuple.get_token_names())))

    def test_full(self):
        init_full_constraints()

        try_helper(
            lambda: Full(tokens=[Token("clashed_name"), Token("clashed_name")]), "used same name twice", ValueError)
        try_helper(
            lambda: Full(edges=[Edge("name1", "name2", [])]), "used undefined names", ValueError)
        try_helper(
            lambda: Full(distances=[ExactDistance("name1", "name2", 0), UptoDistance("name1", "name2", 0)]),
            "used undefined names", ValueError)
        try_helper(
            lambda: Full(concats=[TokenPair({"bla1_bla2"}, "name1", "name2"),
                                  TokenTriplet({"bla1_bla2_bla3"}, "name1", "name2", "name3")]),
            "used undefined names", ValueError)
        try_helper(
            lambda: Full(tokens=[Token("no_child", no_children=True)], edges=[Edge("no_child", "no_child", [])]),
            "Found an edge constraint with a parent token that already has a no_children constraint", ValueError)
        try_helper(
            lambda: Full(tokens=[Token("no_parent", is_root=True)], edges=[Edge("no_parent", "no_parent", [])]),
            "Found an edge constraint with a child token that already has a is_root constraint", ValueError)
        try_helper(
            lambda: Full(tokens=[Token("no_child", no_children=True, outgoing_edges=[HasLabelFromList([""])])]),
            "Found a token with a no_children/is_root constraint and outgoing_edges/incoming_edges constraint",
            ValueError)


class TestMatcher:
    def test_sanity(self):
        conversions = [("conversion1", Full(
            tokens=[Token("tok2"), Token("tok1", spec=[Field(FieldNames.WORD, ["went"])])],
            edges=[Edge("tok1", "tok2", [HasLabelFromList(["some_label"])])]))]
        matcher = Matcher([NamedConstraint(name, constraint) for name, constraint in conversions], nlp.vocab)

        for sent in sentences:
            m = matcher(sent)
            for conv_name in m.names():
                matches = m.matches_for(conv_name)
                for match in matches:
                    assert match.token("tok1") == 1
                    assert match.token("tok2") == 3
                    assert match.edge(1, 3) == {"some_label"}

    def test_get_matched_labels(self):
        assert {"nmod:of", "bla"} == get_matched_labels(
            [HasLabelFromList(["/nmod.*/", "nsubj", "bla"]), HasNoLabel("dobj")], ["nmod:of", "bla"])
        assert set() == get_matched_labels([HasNoLabel("dobj")], ["nsubjpass"])
        assert get_matched_labels(
            [HasLabelFromList(["/nmod.*/", "nsubj", "bla"]), HasNoLabel("dobj")], ["nsubjpass"]) is None
        assert get_matched_labels(
            [HasLabelFromList(["/nmod.*/", "nsubj", "bla"]), HasNoLabel("dobj")], ["nsubj", "dobj"]) is None
        assert get_matched_labels(
            [HasLabelFromList(["/nmod.*/", "nsubj", "bla"]), HasNoLabel("dobj")], ["dobj"]) is None

    def test_filter_distance_constraints(self):
        gm = GlobalMatcher(Full(tokens=[Token("tok1"), Token("tok2"), Token("tok3", optional=True)],
                                distances=[ExactDistance("tok1", "tok2", 0), ExactDistance("tok1", "tok3", 0)]))
        assert gm._filter_distance_constraints({"tok1": 0, "tok2": 1})
        assert not gm._filter_distance_constraints({"tok1": 0, "tok2": 2})

    def test_filter_concat_constraints(self):
        gm = GlobalMatcher(Full(tokens=[Token("tok1"), Token("tok2"), Token("tok3", optional=True)],
                                concats=[TokenPair({"test1_test2"}, "tok1", "tok2"),
                                         TokenPair({"test1_test3"}, "tok1", "tok3")]))
        assert gm._filter_concat_constraints({"tok1": 0, "tok2": 1}, sentences[0])
        assert not gm._filter_concat_constraints({"tok1": 0, "tok2": 2}, sentences[0])

    def test_try_merge(self):
        assert GlobalMatcher._try_merge({"a": 1, "b": 2, "c": 3}, {"b": 2, "c": 3, "d": 4}) == \
            {"a": 1, "b": 2, "c": 3, "d": 4}
        assert GlobalMatcher._try_merge({"a": 1, "b": 2, "c": 3}, {"b": 4, "c": 3, "d": 4}) == {}

    def test_filter_edge_constraints(self):
        # no edge constraint
        gm = GlobalMatcher(Full())
        assert gm._filter_edge_constraints({}, None) == []

        gm = GlobalMatcher(Full(tokens=[Token("tok1"), Token("tok2")],
                                edges=[Edge("tok1", "tok2", [HasLabelFromList(["some_label"])])]))
        # no children
        assert gm._filter_edge_constraints({"tok2": [2]}, None) == []
        # no parents
        assert gm._filter_edge_constraints({"tok1": [2]}, None) == []
        # get_matched_labels returns None (and that's it)
        assert gm._filter_edge_constraints({"tok1": [1], "tok2": [2]}, sentences[0]) == []
        # get_matched_labels returns None (once, but there are more results)
        assert gm._filter_edge_constraints({"tok1": [1], "tok2": [3, 4]}, sentences[0]) == \
               [(False, [{"tok1": 1, "tok2": 3}, {"tok1": 1, "tok2": 4}])]

        # more than one edge_assignments
        gm = GlobalMatcher(Full(tokens=[Token("tok1"), Token("tok2"), Token("tok3")], edges=[
            Edge("tok1", "tok2", [HasLabelFromList(["some_label"])]),
            Edge("tok1", "tok3", [HasLabelFromList(["some_label"])])]))
        assert gm._filter_edge_constraints({"tok1": [1], "tok2": [3, 4], "tok3": [5, 6]}, sentences[0]) == \
               [(False, [{"tok1": 1, "tok2": 3}, {"tok1": 1, "tok2": 4}]), (False, [{"tok1": 1, "tok3": 5}, {"tok1": 1, "tok3": 6}])]

    def test_merge_edges_assignments(self):
        # no edges_assignments
        assert GlobalMatcher._merge_edges_assignments([]) == []
        # big unsuccessful merge
        assert GlobalMatcher._merge_edges_assignments([
            (False, [{"a": 1, "b": 2}, {"a": 1, "b": 3}, {"a": 4, "b": 5}]),
            (False, [{"b": 3, "c": 6}, {"b": 5, "c": 8}, {"b": 7, "c": 9}]),
            (False, [{"e": 100, "f": 200}]),
            (False, [{"c": 10, "d": 11}, {"c": 10, "d": 12}, {"c": 1, "d": 2}])]) == []
        # big successful merge
        assert GlobalMatcher._merge_edges_assignments([
            (False, [{"a": 1, "b": 2}, {"a": 1, "b": 3}, {"a": 4, "b": 5}]),
            (False, [{"b": 3, "c": 6}, {"b": 5, "c": 8}, {"b": 5, "c": 7}, {"b": 7, "c": 9}]),
            (False, [{"e": 100, "f": 200}]),
            (False, [{"c": 6, "d": 11}, {"c": 6, "d": 2}, {"c": 8, "d": 1000}, {"c": 10, "d": 12}, {"c": 1, "d": 2}])]) == \
            [{"a": 1, "b": 3, "c": 6, "d": 11, "e": 100, "f": 200},
             {"a": 1, "b": 3, "c": 6, "d": 2, "e": 100, "f": 200},
             {"a": 4, "b": 5, "c": 8, "d": 1000, "e": 100, "f": 200}]

    def test_gm_apply(self):
        # no merges
        gm = GlobalMatcher(Full())
        assert len(list(gm.apply({}, sentences[0]))) == 0
        # only one merge that fails a distance or concat filter
        gm = GlobalMatcher(Full(tokens=[Token("tok1"), Token("tok2"), Token("tok3", capture=False)],
                                edges=[Edge("tok1", "tok2", [HasLabelFromList(["some_label"])]),
                                       Edge("tok1", "tok3", [HasLabelFromList(["some_label"])])],
                                distances=[ExactDistance("tok1", "tok2", 10)]))
        assert len(list(gm.apply({"tok1": [1], "tok2": [3]}, sentences[0]))) == 0
        # sanity (but have redundant token names so we can validate they are filtered)
        for res in gm.apply({"tok1": [1], "tok2": [12], "tok3": [2]}, sentences[0]):
            assert res.edge(1, 12) == {"some_label"}
            assert res.token("tok1") == 1
            assert res.token("tok2") == 12
            assert res.token("tok3") == -1

    def test_make_patterns(self):
        assert [
                   ("1", False, {"LOWER": {"NOT_IN": ["tok1", "token1"]}, "LEMMA": {"IN": ["tok", "token"]}}),
                   ("2", True, {"TAG": {"NOT_IN": ["VB", "JJ"]}, "ENT_TYPE": {"IN": ["PER", "ORG"]}})] == \
               TokenMatcher._make_patterns([
                   Token("1", optional=True, spec=[
                       Field(in_sequence=False, field=FieldNames.WORD, value=["tok1", "token1"]),
                       Field(in_sequence=True, field=FieldNames.LEMMA, value=["tok", "token"])]),
                   Token("2", spec=[
                       Field(in_sequence=False, field=FieldNames.TAG, value=["VB", "JJ"]),
                       Field(in_sequence=True, field=FieldNames.ENTITY, value=["PER", "ORG"])])])

    def test_post_spacy_matcher(self):
        # empty matched_tokens
        tm = TokenMatcher([], nlp.vocab)
        assert {} == tm._post_spacy_matcher({}, sentences[0])

        # have one no_children with children, have one out_matched/in_matched as None, have one successful token
        tm = TokenMatcher([Token("tok1", no_children=True),
                           Token("tok2", outgoing_edges=[HasNoLabel("some_label")]),
                           Token("tok3")], nlp.vocab)
        assert {"tok2": [5], "tok3": [3, 4]} == \
               tm._post_spacy_matcher({"tok1": [3], "tok2": [3, 5], "tok3": [3, 4]}, sentences[0])

    def test_tm_apply(self):
        # no matches with optional
        tm = TokenMatcher([Token("tok1", optional=True, spec=[Field(FieldNames.WORD, ["by"])])], nlp.vocab)
        assert {} == tm.apply(sentences[1], docs[1])

        # no matches with no optional
        tm = TokenMatcher([Token("tok1", spec=[Field(FieldNames.WORD, ["by"])])], nlp.vocab)
        assert tm.apply(sentences[1], docs[1]) is None

        # matches
        tm = TokenMatcher([Token("tok1", spec=[Field(FieldNames.WORD, ["he"])]),
                           Token("verb", spec=[Field(FieldNames.TAG, ["VBD", "VB"])])], nlp.vocab)
        assert {"tok1": [0], "verb": [1, 3]} == tm.apply(sentences[2], docs[2])


class TestMatch:
    def test_matched_for(self):
        constraint = Full(tokens=[Token("tok1", spec=[Field(FieldNames.WORD, ["by"])])])
        constraint2 = Full(tokens=[Token("tok2"), Token("tok1", spec=[Field(FieldNames.WORD, ["he"])])],
                           edges=[Edge("tok1", "tok2", [HasLabelFromList(["no_label"])])])
        constraint3 = Full(tokens=[Token("tok2"), Token("tok1", spec=[Field(FieldNames.WORD, ["he"])])],
                           edges=[Edge("tok1", "tok2", [HasLabelFromList(["some_label"])])])
        match = Match(
            {"constraint1": TokenMatcher(constraint.tokens, nlp.vocab),
             "constraint2": TokenMatcher(constraint2.tokens, nlp.vocab),
             "constraint3": TokenMatcher(constraint3.tokens, nlp.vocab)},
            {"constraint1": GlobalMatcher(constraint),
             "constraint2": GlobalMatcher(constraint2),
             "constraint3": GlobalMatcher(constraint3)},
            sentences[3], nlp.vocab)
        assert len(list(match.matches_for("constraint1"))) == 0
        assert len(list(match.matches_for("constraint2"))) == 0
        assert len(list(match.matches_for("constraint3"))) == 1
        for m in match.matches_for("constraint3"):
            assert m.token("tok1") == 0
            assert m.token("tok2") == 2
            assert m.edge(0, 2) == {"some_label"}


def test_preprocess_constraint():
    ret = preprocess_constraint(Full(
        tokens=[Token("tok1"), Token("tok2"), Token("tok3")],
        edges=[Edge("tok1", "tok2", [HasLabelFromList(["nsubj"]), HasNoLabel("dobj")]),
               Edge("tok2", "tok3", [HasLabelFromList(["nmod"]), HasNoLabel("xcomp")])],
        concats=[TokenPair({"tok1_tok3"}, "tok1", "tok3"), TokenTriplet({"tok2_tok1_tok3"}, "tok2", "tok1", "tok3")]))
    assert ret.tokens[0].id == "tok1"
    assert ret.tokens[1].id == "tok2"
    assert ret.tokens[2].id == "tok3"
    assert ret.tokens[0].incoming_edges[0].value == ["nsubj"]
    assert ret.tokens[1].outgoing_edges[0].value == ["nsubj"]
    assert ret.tokens[1].incoming_edges[0].value == ["nmod"]
    assert ret.tokens[2].outgoing_edges[0].value == ["nmod"]
    assert ret.tokens[0].spec[0].value == ["tok1"]
    assert ret.tokens[0].spec[0].field == FieldNames.WORD
    assert ret.tokens[1].spec[0].value == ["tok2"]
    assert ret.tokens[1].spec[0].field == FieldNames.WORD
    assert ret.tokens[2].spec[0].value == ["tok3"]
    assert ret.tokens[2].spec[0].field == FieldNames.WORD


