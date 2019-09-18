from .conllu_wrapper import parse_conllu, serialize_conllu, parse_odin, conllu_to_odin
from .converter import convert


def convert_ud2ude_conllu(conllu_text, enhance_ud=True, enhanced_plus_plus=True, enhanced_extra=True, preserve_comments=False, conv_iterations=1):
    parsed, all_comments = parse_conllu(conllu_text)
    converted, _ = convert(parsed, enhance_ud, enhanced_plus_plus, enhanced_extra)
    return serialize_conllu(converted, all_comments, preserve_comments)


def convert_ud2ude_odin(odin_json, enhance_ud=True, enhanced_plus_plus=True, enhanced_extra=True, conv_iterations=1):
    sents = parse_odin(odin_json)
    converted_sents, _ = convert(sents, enhance_ud, enhanced_plus_plus, enhanced_extra)
    converted_odin = conllu_to_odin(converted_sents, False, odin_json)
    
    return converted_odin
