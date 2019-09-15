import chardet
import argparse
import json

import ud2ude_aryehgigi as uda


def api_convert(odin_input, text, enhance_ud, enhacne_plus_plus, enhacne_extra, preserve_comments):
    converted_as_text = ""
    
    if odin_input:
        converted = uda.api.convert_ud2ude_odin(json.loads(text), enhance_ud, enhacne_plus_plus, enhacne_extra)
        converted_as_text = json.dumps(converted)
    else:
        converted_as_text = uda.api.convert_ud2ude_conllu(text, enhance_ud, enhacne_plus_plus, enhacne_extra, preserve_comments)
    
    return converted_as_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    parser.add_argument("-o", "--output_path", help="optional output path (CoNLL-U format), otherwise will print to stdout")
    parser.add_argument("-e", "--enhance_ud", help="enhance ud", action="store_true")
    parser.add_argument("-p", "--enhacne_plus_plus", help="enhance ud++", action="store_true")
    parser.add_argument("-f", "--enhacne_extra", help="enhance aryehs extras", action="store_true")
    parser.add_argument("-i", "--preserve_comments", help="preserve_comments", action="store_true")
    parser.add_argument("-d", "--odin_input", help="the input path is odin json", action="store_true")
    args = parser.parse_args()
    print(args)
    
    # best effort: lets try the most trivial encoding, then, if not successful find the correct encoding.
    try:
        encoding = "utf8"
        with open(args.input_path, "r", encoding=encoding) as f:
            ready_to_write = api_convert(args.odin_input, f.read(), args.enhance_ud, args.enhacne_plus_plus, args.enhacne_extra, args.preserve_comments)
    
    except UnicodeDecodeError:
        encoding = chardet.detect(open(args.input_path, 'rb').read())['encoding']
        with open(args.input_path, "r", encoding=encoding) as f:
            ready_to_write = api_convert(args.odin_input, f.read(), args.enhance_ud, args.enhacne_plus_plus, args.enhacne_extra, args.preserve_comments)
    
    if args.output_path:
        with open(args.output_path, "w", encoding=encoding) as f:
            f.write(ready_to_write)
    else:
        return ready_to_write


if __name__ == "__main__":
    main()
