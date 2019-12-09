from .conllu_wrapper import parse_conllu, serialize_conllu, parse_odin, conllu_to_odin, parsed_tacred_json
from .converter import convert, ConvsCanceler


def convert_ud2ude_conllu(conllu_text, enhance_ud=True, enhanced_plus_plus=True, enhanced_extra=True, preserve_comments=False, conv_iterations=1, remove_eud_info=False, remove_extra_info=False, remove_node_adding_conversions=False, funcs_to_cancel=ConvsCanceler()):
    parsed, all_comments = parse_conllu(conllu_text)
    converted, _ = convert(parsed, enhance_ud, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_eud_info, remove_extra_info, remove_node_adding_conversions, funcs_to_cancel)
    return serialize_conllu(converted, all_comments, preserve_comments)


def _convert_ud2ude_odin_sent(doc, enhance_ud, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_eud_info, remove_extra_info, remove_node_adding_conversions, funcs_to_cancel):
    sents = parse_odin(doc)
    converted_sents, _ = convert(sents, enhance_ud, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_eud_info, remove_extra_info, remove_node_adding_conversions, funcs_to_cancel)
    return conllu_to_odin(converted_sents, doc)


def convert_ud2ude_odin(odin_json, enhance_ud=True, enhanced_plus_plus=True, enhanced_extra=True, conv_iterations=1, remove_eud_info=False, remove_extra_info=False, remove_node_adding_conversions=False, funcs_to_cancel=ConvsCanceler()):
    if "documents" in odin_json:
        for doc_key, doc in odin_json["documents"].items():
            odin_json["documents"][doc_key] = _convert_ud2ude_odin_sent(doc, enhance_ud, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_eud_info, remove_extra_info, remove_node_adding_conversions, funcs_to_cancel)
    else:
        odin_json = _convert_ud2ude_odin_sent(odin_json, enhance_ud, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_eud_info, remove_extra_info, remove_node_adding_conversions, funcs_to_cancel)
    
    return odin_json


def convert_ud2ude_tacred(tacred_json, enhance_ud=True, enhanced_plus_plus=True, enhanced_extra=True, conv_iterations=1, remove_eud_info=False, remove_extra_info=False, remove_node_adding_conversions=False, funcs_to_cancel=ConvsCanceler()):
    sents = parsed_tacred_json(tacred_json)
    converted_sents, _ = convert(sents, enhance_ud, enhanced_plus_plus, enhanced_extra, conv_iterations, remove_eud_info, remove_extra_info, remove_node_adding_conversions, funcs_to_cancel)
    
    return converted_sents


def get_conversion_names():
    return ConvsCanceler.get_conversion_names()
