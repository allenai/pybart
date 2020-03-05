import pathlib
import math
#from pytest import fail

from ud2ude.conllu_wrapper import parse_conllu, serialize_conllu
from ud2ude import converter
from ud2ude import api
from ud2ude.graph_token import add_basic_edges
from ud2ude.converter import convert, ConvsCanceler


class TestConversions:
    test_names = set()
    out = dict()
    gold = dict()
    gold_combined = dict()
    
    @classmethod
    def setup_class(cls):
        global g_remove_enhanced_extra_info, g_remove_aryeh_extra_info
        g_remove_enhanced_extra_info = False
        g_remove_aryeh_extra_info = False
        
        dir_ = str(pathlib.Path(__file__).parent.absolute())
        with open(dir_ + "/handcrafted_tests.conllu") as f:
            text = f.read()
            parsed, all_comments = parse_conllu(text)
        
        for sentence, comments in zip(parsed, all_comments):
            for comment in comments:
                splited = comment.split('# test:')
                if (len(splited) == 2) and (splited[0] == ''):
                    test_name = splited[1].split("-")[0]
                    cls.test_names.add(test_name)
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
    
    # @classmethod
    # def teardown_class(cls):
    #     # global blablabla
    #     # f = open("blablabla.conllu", 'a')
    #     # f.write("".join([blablabla[name_] for name_ in cls.test_names2]))
    #     missing_names = api.get_conversion_names().difference(cls.test_names)
    #     if missing_names:
    #         fail(f"following functions are not covered: {','.join(missing_names)}")

    @classmethod
    def common_logic(cls, cur_name):
        name = cur_name.split("test_")[1]
        tested_func = getattr(converter, name)
        for spec, sent_ in cls.out[name].items():
            sent = {k: v.copy() for k, v in sent_.items()}
            add_basic_edges(sent)
            try:
                tested_func(sent)
            except TypeError:
                iids = dict()
                tested_func(sent, iids)
            serialized_conllu = serialize_conllu([sent], [None], False)
            for gold_line, out_line in zip(cls.gold[name][spec], serialized_conllu.split("\n")):
                assert gold_line == out_line.split(), spec + str([print(s) for s in serialized_conllu.split("\n")])
    
    @classmethod
    def common_logic_combined(cls, cur_name):
        name = cur_name.split("test_combined_")[1]
        for spec, sent_ in cls.out[name].items():
            sent = {k: v.copy() for k, v in sent_.items()}
            add_basic_edges(sent)
            converted, _ = convert([sent], True, True, True, math.inf, False, False, False, False, False, ConvsCanceler())
            serialized_conllu = serialize_conllu(converted, [None], False)
            for gold_line, out_line in zip(cls.gold_combined[name][spec], serialized_conllu.split("\n")):
                assert gold_line == out_line.split(), spec + str([print(s) for s in serialized_conllu.split("\n")])


for cur_func_name in api.get_conversion_names():
    if cur_func_name in ['extra_inner_weak_modifier_verb_reconstruction']:
        continue
    test_func_name = "test_" + cur_func_name
    setattr(TestConversions, test_func_name, staticmethod(lambda func_name=test_func_name: TestConversions.common_logic(func_name)))
    combined_func_name = "test_combined_" + cur_func_name
    setattr(TestConversions, combined_func_name, staticmethod(lambda func_name=combined_func_name: TestConversions.common_logic_combined(func_name)))
