import sys
import chardet
import argparse

import conllu_wrapper as cw
import converter


def main_internal(sentences_text, enhance_only_nmods, enhanced_plus_plus, enhanced_extra, preserve_comments):
    parsed, all_comments = cw.parse_conllu(sentences_text)
    converted = converter.convert(parsed, enhance_only_nmods, enhanced_plus_plus, enhanced_extra)
    return cw.serialize_conllu(converted, all_comments, preserve_comments)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output_path", help="optional output path (CoNLL-U format), otherwise will print to stdout")
    parser.add_argument("-e", "--enhacne_plus_plus", help="enhance ud++", action="store_true")
    parser.add_argument("-f", "--enhacne_extra", help="enhance aryehs extras", action="store_true")
    parser.add_argument("-g", "--enhacne_only_nmods", help="enhance only nmods", action="store_true")
    parser.add_argument("-i", "--preserve_comments", help="preserve_comments", action="store_true")
    args = parser.parse_args()
    print(args)

    # best effort: lets try the most trivial encoding, then, if not successful find the correct encoding.
    try:
        encoding = "utf8"
        with open(args.input_path, "r", encoding=encoding) as f:
            ready_to_write = main_internal(f.read(), args.enhacne_only_nmods, args.enhacne_plus_plus, args.enhacne_extra, args.preserve_comments)
    except UnicodeDecodeError:
        encoding = chardet.detect(open(args.input_path, 'rb').read())['encoding']
        with open(args.input_path, "r", encoding=encoding) as f:
            ready_to_write = main_internal(f.read(), args.enhacne_only_nmods, args.enhacne_plus_plus, args.enhacne_extra, args.preserve_comments)
    
    if args.output_path:
        with open(args.output_path, "w", encoding=encoding) as f:
            f.write(ready_to_write)
    else:
        return ready_to_write


if __name__ == "__main__":
    main()
