from bottle import route, run, post, request, static_file
import json
import subprocess
import main as calc_tree
import conllu_wrapper as cw

ARBITRARY_PATH = "c:/temp/sentence.txt"
ARBITRARY_PATH2 = "c:/temp/bla.txt"


@route('/')
@route('/<filepath:path>')
def server_static(filepath="index.html"):
    return static_file(filepath, root='./public/')


@route('/api/1/annotate', method='POST')
def annotate():
    if request.json is None or "sentence" not in request.json:
        return {"error": "No sentence provided"}
    
    sentence = request.json["sentence"]
    with open(ARBITRARY_PATH, "w") as f:
        f.write(sentence)
    with open(ARBITRARY_PATH2, "w") as f:
        pop = subprocess.Popen("java -cp \"*\" -mx2000m edu.stanford.nlp.parser.lexparser.LexicalizedParser -outputFormat \"conll2007\" edu/stanford/nlp/models/lexparser/englishPCFG.ser.gz %s" % ARBITRARY_PATH, cwd=r"c:\Users\inbaryeh\Documents\academy\Thesis\ai2\stanford-parser-full-2018-10-17", stdout=f, stderr=subprocess.PIPE)
        pop.wait()
    
    conllu_basic_out = open(ARBITRARY_PATH2, "r").read()
    conllu_basic_out_formatted, _ = cw.parse_conllu(conllu_basic_out)
    conllu_plus_out_formatted = calc_tree.main_internal(conllu_basic_out, out_as_raw_test=False)
    odin_basic_out = cw.conllu_to_odin(conllu_basic_out_formatted, is_basic=True)
    odin_plus_out = cw.conllu_to_odin(conllu_plus_out_formatted)
    
    return json.dumps({
        "basic": odin_basic_out,
        "plus": odin_plus_out,
    })


run(host='localhost', reloader=True, port=5000)
