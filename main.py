import sys

import conllu_wrapper as cw
import converter


def main(sentences_path, out_path=None):
    with open(sentences_path, "r") as f:
        sentences_text = f.read()
        parsed, found_ner = cw.parse_conllu(sentences_text)
        converted = converter.convert(parsed, found_ner)
        ready_to_write = cw.serialize_conllu(converted)

    if out_path:
        with open(out_path, "r") as f:
            f.write(ready_to_write)
    else:
        print(ready_to_write)


def print_usage():
    print("Usage: main.py input_path [output_path]\n"
          "Both input and output should and would be in CoNLL-U format.")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        main(sys.argv[1])
    elif len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    else:
        print_usage()
