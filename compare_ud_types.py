import os
from bottle import route, run, request, static_file
import json
import spacy
from spacy_conll import Spacy2ConllParser
import converter
import conllu_wrapper as cw

ARBITRARY_PATH = "sentence.txt"


@route('/')
@route('/<filepath:path>')
def server_static(filepath="index.html"):
    lastpart = filepath[filepath.rfind('/') + 1:]
    if (" " in lastpart) or ("." not in lastpart):
        filepath = filepath.replace(lastpart, "index.html")
    return static_file(filepath, root='./public/')


@route('/api/1/annotate', method='POST')
def annotate():
    if request.json is None or "sentence" not in request.json:
        return {"error": "No sentence provided"}
    
    sentence = request.json["sentence"]
    eud = request.json["eud"]
    eud_pp = request.json["eud_pp"]
    eud_aryeh = request.json["eud_aryeh"]
    
    spacyconll.parseprint(input_str=sentence, output_file=ARBITRARY_PATH, is_tokenized=True)
    with open(ARBITRARY_PATH, "r") as f:
        conllu_basic_out = f.read()
    os.remove(ARBITRARY_PATH)
    
    conllu_basic_out_formatted, _ = cw.parse_conllu(conllu_basic_out)
    conllu_plus_out_formatted = converter.convert(cw.parse_conllu(conllu_basic_out)[0], eud, False, eud_pp, eud_aryeh)

    odin_basic_out = cw.conllu_to_odin(conllu_basic_out_formatted, is_basic=True)
    odin_plus_out = cw.conllu_to_odin(conllu_plus_out_formatted)

    return json.dumps({
        "basic": odin_basic_out,
        "plus": odin_plus_out,
    })


# TODO:
#   1. add to a main function
#   2. copy the model to the project and remove the absolute local path
nlp = spacy.load("model-best")
spacyconll = Spacy2ConllParser(nlp=nlp)
run(host='localhost', reloader=True, port=5020)
