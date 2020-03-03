from ud2ude.conllu_wrapper import parse_conllu, serialize_conllu
from ud2ude import converter
from ud2ude import api
import pathlib
from pytest import fail


class TestConversions:
    test_names = set()
    out = dict()
    gold = dict()
    
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
    
    # @classmethod
    # def teardown_class(cls):
    #     missing_names = api.get_conversion_names().difference(cls.test_names)
    #     if missing_names:
    #         fail(f"following functions are not covered: {','.join(missing_names)}")

    @classmethod
    def common_logic(cls, cur_name):
        name = cur_name.split("test_")[1]
        tested_func = getattr(converter, name)
        for spec, sent in cls.out[name].items():
            try:
                tested_func(sent)
            except TypeError:
                iids = dict()
                tested_func(sent, iids)
            serialized_conllu = serialize_conllu([sent], [None], False)
            for gold_line, out_line in zip(cls.gold[name][spec], serialized_conllu.split("\n")):
                assert gold_line == out_line.split(), spec + str([print(s) for s in serialized_conllu.split("\n")])


for cur_func_name in ['test_eud_correct_subj_pass', 'test_eudpp_process_simple_2wp', 'test_eudpp_process_complex_2wp',
                      'test_eudpp_process_3wp', 'test_eudpp_demote_quantificational_modifiers', 'test_eudpp_expand_pp_or_prep_conjunctions',
                      'test_eud_prep_patterns', 'test_eud_conj_info', 'test_eud_passive_agent', 'test_eudpp_add_ref_and_collapse',
                      'test_eud_subj_of_conjoined_verbs', 'test_eud_heads_of_conjuncts', 'test_eud_xcomp_propagation',
                      'test_extra_aspectual_reconstruction', 'test_extra_xcomp_propagation_no_to', 'test_extra_advcl_propagation',
                      'test_extra_advcl_ambiguous_propagation', 'test_extra_dep_propagation', 'test_extra_acl_propagation',
                      'test_extra_conj_propagation_of_nmods']:
# for cur_func_name in api.get_conversion_names():
#     if cur_func_name in ['extra_inner_weak_modifier_verb_reconstruction']:
#         continue
#     cur_func_name = "test_" + cur_func_name
    setattr(TestConversions, cur_func_name, staticmethod(lambda func_name=cur_func_name: TestConversions.common_logic(func_name)))
