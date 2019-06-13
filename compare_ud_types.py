from bottle import route, run, request, static_file
import json
import spacy
from spacy_conll import Spacy2ConllParser
import main as calc_tree
import conllu_wrapper as cw

ARBITRARY_PATH = "c:/temp/sentence.txt"


@route('/')
@route('/<filepath:path>')
def server_static(filepath="index.html"):
    if ("/" not in filepath) and (filepath != "index.html") and (filepath != "favicon.ico"):
        filepath = "index.html"
    return static_file(filepath, root='./public/')


@route('/api/1/annotate', method='POST')
def annotate():
    if request.json is None or "sentence" not in request.json:
        return {"error": "No sentence provided"}
    
    sentence = request.json["sentence"]
    spacyconll.parseprint(input_str=sentence, output_file=ARBITRARY_PATH, is_tokenized=True)
    with open(ARBITRARY_PATH, "r") as f:
        conllu_basic_out = f.read()

    conllu_basic_out_formatted, _ = cw.parse_conllu(conllu_basic_out)
    conllu_plus_out_formatted = calc_tree.main_internal(conllu_basic_out, out_as_raw_text=False)
    odin_basic_out = cw.conllu_to_odin(conllu_basic_out_formatted, sentence, is_basic=True)
    odin_plus_out = cw.conllu_to_odin(conllu_plus_out_formatted, sentence)
    
    return json.dumps({
        "basic": odin_basic_out,
        "plus": odin_plus_out,
    })


# TODO:
#   1. add to a main function
#   2. copy the model to the project and remove the absolute local path
nlp = spacy.load(r"C:\temp\ud_for_spacy\attempt2-edited_punct_combined\models\model-final")
spacyconll = Spacy2ConllParser(nlp=nlp)
run(host='localhost', reloader=True, port=5020)
