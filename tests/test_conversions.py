import pathlib
import math
#from pytest import fail

import pybart
from pybart.conllu_wrapper import parse_conllu, serialize_conllu
from pybart import converter
from pybart import api
from pybart.graph_token import add_basic_edges
from pybart.converter import convert


class TestConversions:
    out = dict()
    gold = dict()
    gold_combined = dict()
    
    @classmethod
    def setup_class(cls):
        dir_ = str(pathlib.Path(__file__).parent.absolute())
        with open(dir_ + "/handcrafted_tests.conllu") as f:
            text = f.read()
            parsed, all_comments = parse_conllu(text)
        
        for sentence, comments in zip(parsed, all_comments):
            for comment in comments:
                splited = comment.split('# test:')
                if (len(splited) == 2) and (splited[0] == ''):
                    test_name = splited[1].split("-")[0]
                    specification = splited[1].split("-")[1]
                    if test_name in cls.out:
                        cls.out[test_name][specification] = sentence
                    else:
                        cls.out[test_name] = {specification: sentence}
        
        test_name = ""
        specification = ""
        for output, cur_gold in zip(["/expected_handcrafted_tests_output.conllu", "/expected_handcrafted_tests_output_combined.conllu"], [cls.gold, cls.gold_combined]):
            for gold_line in open(dir_ + output, 'r').readlines():
                if gold_line.startswith('#'):
                    if gold_line.split(":")[0] == "# test":
                        test_name = gold_line.split(":")[1].split("-")[0]
                        specification = gold_line.split(":")[1].split("-")[1].strip()
                    continue
                elif gold_line.startswith('\n'):
                    continue
                else:
                    if test_name in cur_gold:
                        if specification in cur_gold[test_name]:
                            cur_gold[test_name][specification].append(gold_line.split())
                        else:
                            cur_gold[test_name][specification] = [gold_line.split()]
                    else:
                        cur_gold[test_name] = {specification: [gold_line.split()]}
    
    @staticmethod
    def setup_method():
        pybart.converter.g_remove_enhanced_extra_info = False
        pybart.converter.g_remove_bart_extra_info = False
        pybart.converter.g_remove_node_adding_conversions = False
    
    @classmethod
    def common_logic(cls, cur_name):
        name = cur_name.split("test_")[1]
        for spec, sent_ in cls.out[name].items():
            sent = {k: v.copy() for k, v in sent_.items()}
            add_basic_edges(sent)
            converted, _ = convert([sent], True, True, True, math.inf, False, False, False, False, False,
                                   funcs_to_cancel=list(set(api.get_conversion_names()).difference({name})))
            serialized_conllu = serialize_conllu([sent], [None], False)
            for gold_line, out_line in zip(cls.gold[name][spec], serialized_conllu.split("\n")):
                assert gold_line == out_line.split(), spec + str([print(s) for s in serialized_conllu.split("\n")])
    
    @classmethod
    def common_logic_combined(cls, cur_name, rnac=False):
        name = cur_name.split("test_combined_")[1]
        for spec, sent_ in cls.out[name].items():
            sent = {k: v.copy() for k, v in sent_.items()}
            add_basic_edges(sent)
            converted, _ = \
                convert([sent], True, True, True, math.inf, False, False, rnac, False, False, funcs_to_cancel=[])
            serialized_conllu = serialize_conllu(converted, [None], False)
            for gold_line, out_line in zip(cls.gold_combined[name][spec], serialized_conllu.split("\n")):
                assert gold_line == out_line.split(), spec + str([print(s) for s in serialized_conllu.split("\n")])

    def test_no_node_adding(self):
        self.common_logic_combined("test_combined_no_node_adding", rnac=True)


for cur_func_name in api.get_conversion_names():
    if cur_func_name in ['extra_inner_weak_modifier_verb_reconstruction']:
        continue
    test_func_name = "test_" + cur_func_name
    setattr(TestConversions, test_func_name, staticmethod(lambda func_name=test_func_name: TestConversions.common_logic(func_name)))
    combined_func_name = "test_combined_" + cur_func_name
    setattr(TestConversions, combined_func_name, staticmethod(lambda func_name=combined_func_name: TestConversions.common_logic_combined(func_name)))
