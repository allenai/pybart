from ud2ude.conllu_wrapper import parse_conllu, serialize_conllu
from ud2ude import converter
from ud2ude import api
import pathlib
from pytest import fail


class TestConversions:
    test_names = set()
    
    @classmethod
    def setup_class(cls):
        global g_remove_enhanced_extra_info, g_remove_aryeh_extra_info
        g_remove_enhanced_extra_info = False
        g_remove_aryeh_extra_info = False
        
        dir_ = str(pathlib.Path(__file__).parent.absolute())
        with open(dir_ + "/handcrafted_tests.conllu") as f:
            text = f.read()
            parsed, all_comments = parse_conllu(text)
        
        cls.out = dict()
        for sentence, comments in zip(parsed, all_comments):
            for comment in comments:
                splited = comment.split('# test:')
                if len(splited) > 1:
                    test_name = splited[1].split("-")[0]
                    cls.test_names.add(test_name)
                    specification = splited[1].split("-")[1]
                    if test_name in cls.out:
                        cls.out[test_name][specification] = sentence
                    else:
                        cls.out[test_name] = {specification: sentence}
        
        cls.gold = dict()
        test_name = ""
        specification = ""
        for gold_line in open(dir_ + "/expected_handcrafted_tests_output.conllu", 'r').readlines():
            if gold_line.startswith('#'):
                if gold_line.split(":")[0] == "# test":
                    test_name = gold_line.split(":")[1].split("-")[0]
                    specification = gold_line.split(":")[1].split("-")[1].strip()
                continue
            elif gold_line.startswith('\n'):
                continue
            else:
                if test_name in cls.gold:
                    if specification in cls.gold[test_name]:
                        cls.gold[test_name][specification].append(gold_line.split())
                    else:
                        cls.gold[test_name][specification] = [gold_line.split()]
                else:
                    cls.gold[test_name] = {specification: [gold_line.split()]}

    @classmethod
    def teardown_class(cls):
        missing_names = api.get_conversion_names().difference(cls.test_names)
        if missing_names:
            fail(f"following functions are not covered: {','.join(missing_names)}")
    
    def _inner_logic(self, name, tested_func):
        for spec, sent in self.out[name].items():
            tested_func(sent)
            serialized_conllu = serialize_conllu([sent], [None], False)
            for gold_line, out_line in zip(self.gold[name][spec], serialized_conllu.split("\n")):
                assert gold_line == out_line.split()
    
    def test_eud_correct_subj_pass(self):
        name = self.test_eud_correct_subj_pass.__name__.split("test_")[1]
        tested_func = converter.eud_correct_subj_pass
        self._inner_logic(name, tested_func)
    
    def test_eudpp_process_simple_2wp(self):
        name = self.test_eudpp_process_simple_2wp.__name__.split("test_")[1]
        tested_func = converter.eudpp_process_simple_2wp
        self._inner_logic(name, tested_func)
    
    def test_eudpp_process_complex_2wp(self):
        name = self.test_eudpp_process_complex_2wp.__name__.split("test_")[1]
        tested_func = converter.eudpp_process_complex_2wp
        self._inner_logic(name, tested_func)
    
    def test_eudpp_process_3wp(self):
        name = self.test_eudpp_process_3wp.__name__.split("test_")[1]
        tested_func = converter.eudpp_process_3wp
        self._inner_logic(name, tested_func)
    
    def test_eudpp_demote_quantificational_modifiers(self):
        name = self.test_eudpp_demote_quantificational_modifiers.__name__.split("test_")[1]
        tested_func = converter.eudpp_demote_quantificational_modifiers
        self._inner_logic(name, tested_func)
    
    # def test_eudpp_expand_pp_or_prep_conjunctions(self):
    #     name = self.test_eudpp_expand_pp_or_prep_conjunctions.__name__.split("test_")[1]
    #     tested_func = converter.eudpp_expand_pp_or_prep_conjunctions
    #     self._inner_logic(name, tested_func)
