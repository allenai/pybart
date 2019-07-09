import time
import sys
import json
import chardet
import spacy
import en_core_web_lg
from spacy.lemmatizer import Lemmatizer
from spacy.lang.en import LEMMA_INDEX, LEMMA_EXC, LEMMA_RULES
lemmatizer = Lemmatizer(LEMMA_INDEX, LEMMA_EXC, LEMMA_RULES)
nlp = spacy.load('model-best')
nlp2 = en_core_web_lg.load()


tag_map = {
    ".": "PUNCT",
    ",": "PUNCT",
    "``": "PUNCT",
    "-LRB-": "PUNCT",
    "-RRB-": "PUNCT",
    '""': "PUNCT",
    "''": "PUNCT",
    ":":  "PUNCT",
    "$":  "SYM",
    "#": "SYM",
    "AFX": "X",
    "CC": "CCONJ",
    "CD": "NUM",
    "DT": "DET",
    "EX": "PRON",
    "FW": "X",
    "HYPH": "PUNCT",
    "IN": "ADP",
    "JJ": "ADJ",
    "JJR": "ADJ",
    "JJS": "ADJ",
    "LS": "X",
    "MD": "AUX",
    "NIL": "",
    "NN": "NOUN",
    "NNP": "PROPN",
    "NNPS": "PROPN",
    "NNS": "NOUN",
    "PDT": "DET",
    "POS": "PART",
    "PRP": "PRON",
    "PRP$": "PRON",
    "RB": "ADV",
    "RBR": "ADV",
    "RBS": "ADV",
    "RP": "ADP",
    "SP": "SPACE",
    "SYM": "SYM",
    "TO": "PART",
    "UH": "INTJ",
    "VB": "VERB",
    "VBD": "VERB",
    "VBG": "VERB",
    "VBN": "VERB",
    "VBP": "VERB",
    "VBZ": "VERB",
    "WDT": "PRON",
    "WP": "PRON",
    "WP$": "PRON",
    "WRB": "ADV",
    "ADD": "X",
    "NFP": "PUNCT",
    "GW": "X",
    "XX": "X",
    "BES": "VERB",
    "HVS": "VERB",
    "_SP": "SPACE",
}


def custom_sentencizer(doc):
    for i, token in enumerate(doc[:-1]):
        # Define sentence start if pipe
        if (token.tag_ == ".") and (doc.text[token.idx - 1: token.idx] == " ") and (doc.text[token.idx + len(token): token.idx + len(token) + 1] == " "):
            doc[i + 1].is_sent_start = True
        else:
            # Explicitly set sentence start to False otherwise, to tell
            # the parser to leave those tokens alone
            doc[i + 1].is_sent_start = False
    return doc


nlp.add_pipe(custom_sentencizer, before="parser")
nlp2.add_pipe(custom_sentencizer, before="parser")
nlp2.remove_pipe("parser")


def spacy_json2odinson_json(spacy_doc, doc_name, x):
    spacy_doc_text = spacy_doc.text
    odinson_json = {"text": spacy_doc_text, "sentences": [], "id": doc_name}
    starts = [sent.start_char for sent in spacy_doc.sents]
    entities = {range(t.idx, t.idx + len(t.text)): t.ent_type_ for t in nlp2(spacy_doc_text)}
    i = -1
    tokens_shift = 0
    for token in spacy_doc:
        token_end = token.idx + len(token.text)
        if token.idx in starts:
            tokens_shift += len(odinson_json["sentences"][i]["words"]) if i >= 0 else 0
            odinson_json["sentences"].append({"words": [], "raw": [], "startOffsets": [], "endOffsets": [], "tags": [], "lemmas": [], "entities": [], "graphs": {"universal-basic": {"edges": [], "roots": []}}})
            i += 1
        odinson_json["sentences"][i]["words"].append(spacy_doc_text[token.idx: token_end])
        odinson_json["sentences"][i]["raw"].append(spacy_doc_text[token.idx: token_end])
        odinson_json["sentences"][i]["startOffsets"].append(token.idx)
        odinson_json["sentences"][i]["endOffsets"].append(token_end)
        odinson_json["sentences"][i]["tags"].append(token.tag_)
        lemmas = lemmatizer(spacy_doc_text[token.idx: token_end], tag_map[token.tag_])
        odinson_json["sentences"][i]["lemmas"].append(lemmas[0])
        ent = [v for k, v in entities.items() if token.idx in k][0]
        odinson_json["sentences"][i]["entities"].append("O" if ent == "" else ent)
        if token.i == token.head.i:
            odinson_json["sentences"][i]["graphs"]["universal-basic"]["roots"].append(token.i - tokens_shift)
        else:
            odinson_json["sentences"][i]["graphs"]["universal-basic"]["edges"].append({"source": token.head.i - tokens_shift, "destination": token.i - tokens_shift, "relation": token.dep_})
    
    if i != (x - 1):
        print("wrong number of sentences(doc_name, n_sents): %s %d" % (doc_name, i))
    
    return odinson_json


def parse_to_json(in_path, out_path, idx, odinson_json=False):
    start = time.time()
    para = []
    x = 500
    f = open(in_path, 'rb')
    enc = chardet.detect(f.read())['encoding']
    f.close()
    with open(in_path, "r", encoding=enc) as f:
        lines = f.readlines()
        prev_i = 0
        for i, l in enumerate(lines):
            if (i % x == 0) and (i != 0):
                para.append("".join(lines[prev_i:i]).replace("\n", " "))
                prev_i = i
        last = "".join(lines[prev_i:]).replace("\n", " ")
        if last:
            para.append(last)
        
        for i, doc in enumerate(nlp.pipe(para, batch_size=40)):  # TODO replace with parse(line, nlp) when time is not an issue
            if odinson_json:
                out_json = spacy_json2odinson_json(doc, "wiki%d_%d" % (idx, i), x)
            else:
                out_json = doc.to_json()
            with open(out_path + "wiki%d_%d.json" % (idx, i), "w", encoding=enc) as f2:
                json.dump(out_json, f2)
            if i == 0:
                print(time.time() - start)
            if i % int((len(lines) / x) / 100) == 0:
                print("proc:%d, completed:%d%%" % (idx, int((i * 100) / int(len(lines) / x))))


def main(idx):
    start = time.time()
    parse_to_json('../text/wiki_{:0>2}'.format(idx), "../docs/", idx, odinson_json=True)
    print("idx: %d, time: %.2f" % (idx, time.time() - start))


if __name__ == "__main__":
    main(int(sys.argv[1]))
