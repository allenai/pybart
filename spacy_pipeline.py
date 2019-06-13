import time

import sys
import json
import spacy
from spacy.lemmatizer import Lemmatizer
from spacy.lang.en import LEMMA_INDEX, LEMMA_EXC, LEMMA_RULES
lemmatizer = Lemmatizer(LEMMA_INDEX, LEMMA_EXC, LEMMA_RULES)
nlp = spacy.load('model-best')


def custom_sentencizer(doc):
    for i, token in enumerate(doc[:-2]):
        # Define sentence start if pipe
        if token.text == "?":
            doc[i+1].is_sent_start = True
        else:
            # Explicitly set sentence start to False otherwise, to tell
            # the parser to leave those tokens alone
            doc[i+1].is_sent_start = False
    return doc


nlp.add_pipe(custom_sentencizer, before="parser")


def parse(text):
    return nlp(text)


def spacy_json2odinson_json(spacy_json):
    odinson_json = {"text": spacy_json['text'], "sentences": [], "id": "0"}
    starts = [sent['start'] for sent in spacy_json['sents']]
    i = -1
    spacy_json['text'] = spacy_json['text'].replace("?", ".")
    for token in spacy_json['tokens']:
        if token['start'] in starts:
            odinson_json["sentences"].append({"words": [], "raw": [], "startOffsets": [], "endOffsets": [], "tags": [], "lemmas": [], "graphs": {"universal-basic": {"edges": [], "roots": []}}})
            i += 1
        odinson_json["sentences"][i]["words"].append(spacy_json['text'][token['start']: token['end']])
        odinson_json["sentences"][i]["raw"].append(spacy_json['text'][token['start']: token['end']])
        odinson_json["sentences"][i]["startOffsets"].append(token['start'])
        odinson_json["sentences"][i]["endOffsets"].append(token['end'])
        odinson_json["sentences"][i]["tags"].append(token['tag'])
        lemmas = lemmatizer(spacy_json['text'][token['start']: token['end']], token['pos'])
        odinson_json["sentences"][i]["lemmas"].append(lemmas[0] if lemmas[0] != "?" else ".")
        if token['id'] == token['head']:
            odinson_json["sentences"][i]["graphs"]["universal-basic"]["roots"].append(token['id'])
        else:
            odinson_json["sentences"][i]["graphs"]["universal-basic"]["edges"].append({"source": token['id'], "destination": token['head'], "relation": token['dep']})
    
    return odinson_json


def parse_to_json(in_path, out_path, idx, odinson_json=False):
    with open(in_path, "r") as f:
        lines = f.readlines()
        para = []
        prev_i = 0
        for i, l in enumerate(lines):
            if (i % 1000 == 0) and (i != 0):
                para.append("".join(lines[prev_i:i]).replace(" \n", "? "))
                prev_i = i
        last = "".join(lines[prev_i:]).replace(" \n", "? ")
        if last:
            para.append(last)
        
        for i, doc in enumerate(nlp.pipe(para, batch_size=500)):  # TODO replace with parse(line, nlp) when time is not an issue
            if odinson_json:
                out_json = spacy_json2odinson_json(doc.to_json())
            else:
                out_json = doc.to_json()
            with open(out_path + "temp%d_%d.json" % (idx, i), "w") as f2:
                json.dump(out_json, f2)
            if i % 50 == 0:
                print("proc:%d, completed:%d%%" % (idx, int((i * 100) / 5000)))
        

def main(idx):
    start = time.time()
    parse_to_json("text/wiki_%d.txt" % idx, "docs/", idx, odinson_json=True)
    print("idx: %d, time: %.2f" % (idx, time.time() - start))


if __name__ == "__main__":
    main(int(sys.argv[1]))
