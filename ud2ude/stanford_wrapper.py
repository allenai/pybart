from stanfordnlp.pipeline.processor import UDProcessor
from stanfordnlp.pipeline.doc import Word, Document
from stanfordnlp.pipeline._constants import *

from .converter import convert, ConvsCanceler
from .graph_token import Token, add_basic_edges, parse_bart_label


def parse_stanford_sent(sent):
    sentence = dict()
    
    for i, word in enumerate(sent._words):
        # add current token to current sentence
        sentence[word._index] = Token(
            word._index, word._text, word._lemma_, word._upos, word._xpos, "_",
            (word._governor) if word._governor != i + 1 else 0, word._dependency_relation.lower(), "_", "_")
    
    # add root
    sentence[0] = Token(0, None, None, None, None, None, None, None, None, None)
    
    # after parsing entire sentence, add basic deprel edges,
    # and add sentence to output list
    add_basic_edges(sentence)
    
    return sentence


class BartProcessor(UDProcessor):
    PROVIDES_DEFAULT = set(["bart"])
    REQUIRES_DEFAULT = set([TOKENIZE, POS, LEMMA, DEPPARSE])
    
    def __init__(self, config, pipeline, use_gpu, bart_config):
        super(UDProcessor, self).__init__(config, pipeline, use_gpu)
        self.bart_config = bart_config
        
    def _set_up_model(self, config, use_gpu):
        pass
    
    def dummy(self):
        pass
    
    def process(self, doc):
        doc.load_annotations()
        for sentence in doc.sentences:
            converted = convert([parse_stanford_sent(sentence)], *self.bart_config)
            for word in sentence._words:
                word.bart_parent_list = [word.text]
        doc.load_annotations = self.dummy


def add_bart_to_pipe(nlp, bart_config):
    nlp.processor_names.append('bart')
    nlp.config['processors'] += 'bart'
    curr_processor_config = nlp.filter_config('bart', nlp.config)
    curr_processor_config .update({'lang': nlp.config['lang'], 'shorthand': nlp.config['shorthand'], 'mode': 'predict'})
    nlp.processors['bart'] = BartProcessor(config=curr_processor_config , pipeline=nlp, use_gpu=nlp.use_gpu, bart_config=bart_config)


