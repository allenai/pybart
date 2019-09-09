import chardet
import argparse
import json

from .conllu_wrapper import parse_conllu, serialize_conllu, parse_odin, conllu_to_odin
from .converter import convert


def main_internal(sentences_text, enhance_ud, enhanced_plus_plus, enhanced_extra, preserve_comments=False):
    parsed, all_comments = parse_conllu(sentences_text)
    converted = convert(parsed, enhance_ud, enhanced_plus_plus, enhanced_extra)
    return serialize_conllu(converted, all_comments, preserve_comments)


def main_internal_odin(odin_text, enhance_ud, enhanced_plus_plus, enhanced_extra, preserve_comments=False):
    odin_json = json.loads(odin_text)
    sents = parse_odin(odin_json)
    converted_sents = convert(sents, enhance_ud, enhanced_plus_plus, enhanced_extra)
    od = conllu_to_odin(converted_sents, False, odin_json)
    
    return json.dumps(od)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output_path", help="optional output path (CoNLL-U format), otherwise will print to stdout")
    parser.add_argument("-e", "--enhacne_ud", help="enhance ud", action="store_true")
    parser.add_argument("-p", "--enhacne_plus_plus", help="enhance ud++", action="store_true")
    parser.add_argument("-f", "--enhacne_extra", help="enhance aryehs extras", action="store_true")
    parser.add_argument("-i", "--preserve_comments", help="preserve_comments", action="store_true")
    parser.add_argument("-d", "--odin_input", help="the input path is odin json", action="store_true")
    args = parser.parse_args()
    print(args)

    internal = main_internal
    if args.odin_input:
        internal = main_internal_odin

    # best effort: lets try the most trivial encoding, then, if not successful find the correct encoding.
    try:
        encoding = "utf8"
        with open(args.input_path, "r", encoding=encoding) as f:
            ready_to_write = internal(f.read(), args.enhance_ud, args.enhacne_plus_plus, args.enhacne_extra, args.preserve_comments)
            
    except UnicodeDecodeError:
        encoding = chardet.detect(open(args.input_path, 'rb').read())['encoding']
        with open(args.input_path, "r", encoding=encoding) as f:
            ready_to_write = internal(f.read(), args.enhance_ud, args.enhacne_plus_plus, args.enhacne_extra, args.preserve_comments)
    
    if args.output_path:
        with open(args.output_path, "w", encoding=encoding) as f:
            f.write(ready_to_write)
    else:
        return ready_to_write


if __name__ == "__main__":
    main()
