import math
from pybart.new_matcher import *
import spacy

# nlp = spacy.load("en_ud_model_sm")


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
            lambda: Full(tokens=[Token("no_child", no_children=True, outgoing_edges=[HasLabelFromList([""])])]),
            "Found a token with a no_children constraint and outgoing HasLabelFromList constraint", ValueError)


class TestMatcher:
    # def test_sanity(self):
    #     conversions = [("conversion1", init_full_constraints()[0]), ("conversion2", init_full_constraints()[1])]
    #     matcher = Matcher([NamedConstraint(name, constraint) for name, constraint in conversions], nlp.vocab)
    #
    #     docs = [nlp("bla1 bla2 bla3"), nlp("TODO2")]  # TODO
    #
    #     for doc in docs:
    #         m = matcher(doc)
    #         for conv_name in m.names():
    #             matches = m.matches_for(conv_name)
    #             # for match in matches:
    #             #     print(match)
    #             #     print(match.token("token1"), match.token("token2"),
    #             #           match.edge(match.token("token1"), match.token("token2")))

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
        assert gm._filter_concat_constraints({"tok1": 0, "tok2": 1}, TestSentence())
        assert not gm._filter_concat_constraints({"tok1": 0, "tok2": 2}, TestSentence())


class TestSentence:
    # TODO - this is temporary until we have real sentence class
    spec = {0: "test1", 1: "test2", 2: "test3"}

    def get_text(self, i):
        return self.spec[i]
