from typing import Tuple, List
import argparse
import errno
import os
import networkx as nx
import json
import pickle
import time
import pathlib

from collections import defaultdict
from spike.rest.definitions import Relation
from spike.pattern_generation.gen_pattern import PatternGenerator
from spike.pattern_generation.pattern_selectors import LabelEdgeSelector, WordNodeSelector, LemmaNodeSelector, TriggerVarNodeSelector
from spike.pattern_generation.utils import GenerationFromAnnotatedSamples
from spike.pattern_generation.compilation import spike_compiler
from spike.pattern_generation.sample_types import AnnotatedSample
from spike.pattern_generation.compilation.odinson_compiler import compile_to_odinson_rule
from spike.datamodel.dataset import FileBasedDataSet
from spike.evaluation import eval

from pybart import converter, conllu_wrapper as cw, api as uda_api
import spacy
from spacy.tokens import Doc

spike_relations = ['org:alternate_names', 'org:city_of_headquarters', 'org:country_of_headquarters', 'org:dissolved', 'org:founded', 'org:founded_by', 'org:member_of', 'org:members', 'org:number_of_employees_members', 'org:parents', 'org:political_religious_affiliation', 'org:shareholders', 'org:stateorprovince_of_headquarters', 'org:subsidiaries', 'org:top_members_employees', 'org:website', 'per:age', 'per:alternate_names', 'per:cause_of_death', 'per:charges', 'per:children', 'per:cities_of_residence', 'per:city_of_birth', 'per:city_of_death', 'per:countries_of_residence', 'per:country_of_birth', 'per:country_of_death', 'per:date_of_birth', 'per:date_of_death', 'per:employee_of', 'per:origin', 'per:other_family', 'per:parents', 'per:religion', 'per:schools_attended', 'per:siblings', 'per:spouse', 'per:stateorprovince_of_birth', 'per:stateorprovince_of_death', 'per:stateorprovinces_of_residence', 'per:title']
MAX_CONVS = 10  # enough to simpulate infinte, but with less chances for an infinite loop bug..

g_triggers = "triggers/"

def prevent_sentence_boundary_detection(doc):
    for token in doc:
        # This will entirely disable spaCy's sentence detection
        token.is_sent_start = False
    return doc


# loading our spacy model that we trained using UD-format ('cause spacy dont support UD)
# NOTE: look atour project for installing the newest model.
nlp = spacy.load("en_ud_model")
nlp.add_pipe(prevent_sentence_boundary_detection, name='prevent-sbd', before='parser')
tagger = nlp.get_pipe('tagger')
sbd_preventer = nlp.get_pipe('prevent-sbd')
parser = nlp.get_pipe('parser')


######################################### Annotation #########################################


# using the TACRED json to form the basis of the ODIN json
def build_odin_json(tokens, sample_, rel, tags, lemmas, entities, chunks, odin_id):
    start_offsets = []
    end_offsets = []
    offset = 0
    for tok in tokens:
        start_offsets.append(offset)
        end_offsets.append(offset + len(tok))
        offset += len(tok) + len(" ")
    
    start = min(sample_["subj_start"], sample_["obj_start"])
    end = max(sample_["subj_end"] + 1, sample_["obj_end"] + 1)
    tokens_for_text = tokens[start:end]
    
    gold = {"id": "gold_relation_{}".format(odin_id), "text": " ".join(tokens_for_text),
            'tokenInterval': {'start': start, 'end': end},
            "keep": True, "foundBy": "tacred_gold", "type": "RelationMention", "labels": [rel],
            "sentence": 0, "document": "document", "arguments":
                {"subject": [{"type": "TextBoundMention", "sentence": 0, "labels": [sample_["subj_type"]],
                              "tokenInterval": {"start": sample_["subj_start"], "end": sample_["subj_end"] + 1},
                              'id': 'subject_gold_ent_{}'.format(odin_id),
                              'text': " ".join(tokens[sample_["subj_start"]: sample_["subj_end"] + 1]),
                              'document': 'document', 'keep': True, 'foundBy': 'tacred_gold'}],
                 "object": [{"type": "TextBoundMention", "sentence": 0, "labels": [sample_["obj_type"]],
                             "tokenInterval": {"start": sample_["obj_start"], "end": sample_["obj_end"] + 1},
                             'id': 'object_gold_ent_{}'.format(odin_id),
                             'text': " ".join(tokens[sample_["obj_start"]: sample_["obj_end"] + 1]),
                             'document': 'document', 'keep': True, 'foundBy': 'tacred_gold'}]}}
    
    odin_json = {
        "documents": {
            "": {
                "id": str(odin_id),
                "text": " ".join(tokens),
                "sentences": [{"words": tokens, "raw": tokens, "tags": tags, "lemmas": lemmas, "entities": entities,
                               "chunks": chunks, "startOffsets": start_offsets, "endOffsets": end_offsets}],
                "gold_relations": [gold]
            }
        }, "mentions": []}
    
    return odin_json


# tacred has human annotated entities for the relation.
#   but these entities are not well marked in the ner field, how awkward, so we fix it.
def fix_entities(sample, pad):
    entities = sample['stanford_ner'] + (["O"] * (pad - len(sample['stanford_ner'])))
    
    for i in range(sample['subj_start'], sample['subj_end'] + 1):
        entities[i] = sample['subj_type']
    
    for i in range(sample['obj_start'], sample['obj_end'] + 1):
        entities[i] = sample['obj_type']
    
    return entities


# looks for triggers in the setnence (snd not as part of the two entities of the relation - which doesnt make sense)
def search_triggers(subj_start, subj_end, obj_start, obj_end, rel, tokens):
    trigger_toks = []
    for trigger in get_triggers(rel):
        for trigger_start, token in enumerate(tokens):
            trigger_end = trigger_start + len(trigger.split())
            if (trigger.split() == tokens[trigger_start : trigger_end]) and \
               (trigger_end <= subj_start or trigger_start >= subj_end) and \
               (trigger_end <= obj_start or trigger_start >= obj_end):
                   trigger_toks.append((trigger_start, trigger_end))
    return trigger_toks if trigger_toks else [None]


class SampleBARTAnnotator(object):
    @staticmethod
    def annotate_sample(sample_: dict, rel: str, enhance_ud: bool, enhanced_plus_plus: bool, enhanced_bart: bool, convs: int,
                        remove_eud_info: bool, remove_extra_info: bool, odin_id: int = -1, use_triggers: bool = True, ablation: str = "") -> Tuple[List[AnnotatedSample], dict]:
        # NOTE: we dont feed the 'nlp' with the sentence, because we want to get the exact word spliting as the original tacred split,
        #   the same goes for sentence spilting, so we prevent it.
        # NOTE: This code is before we added the option for pyBART to be added to spacy pipline, so we simply run it after the parser.
        doc = Doc(nlp.vocab, words=sample_['token'])
        _ = tagger(doc)
        _ = sbd_preventer(doc)
        _ = parser(doc)
        conllu_basic_out_formatted = cw.parse_spacy_doc(doc)
        sent, iters = converter.convert([conllu_basic_out_formatted], enhance_ud, enhanced_plus_plus, enhanced_bart, convs,
                                    remove_eud_info, remove_extra_info, False, converter.ConvsCanceler([ablation]) if ablation else converter.ConvsCanceler())
        
        assert len(sent) == 1
        sent = sent[0]
        _ = sent.pop(0) # for internal use, we remove the stub root-node
        sent = cw.fix_sentence(sent) # push added nodes to end of sentence (to be aligned with the original sentence
        tokens = [node.get_conllu_field("form") for node in sent.values()] # get words
        tags = [node.get_conllu_field("xpos") for node in sent.values()] # get tags
        lemmas = [node.get_conllu_field("lemma") for node in sent.values()] # get lemmas
        entities = fix_entities(sample_, len(tokens)) # fix the entities of the relation (see exlaination in the function)
        chunks = ["O"] * len(tokens) # chunks - not interesting
        
        # create a networkX graph from the returned bart graph. one multidi and one note - for later use.
        g = nx.Graph()
        mdg = nx.MultiDiGraph()
        for node in sent.values():
            for parent, label in node.get_new_relations():
                if parent.get_conllu_field("id") == 0:
                    continue
                
                g.add_edge(parent.get_conllu_field("id") - 1, node.get_conllu_field("id") - 1, label=label)
                mdg.add_edge(parent.get_conllu_field("id") - 1, node.get_conllu_field("id") - 1, label=label)
        
        # we need this odin format for Spike's 'Index'-ing
        # pyBART supports converting to odin but we rather have the basic information ready in an odin formaat,
        #   and then just change it slightly
        odin_json = build_odin_json(tokens, sample_, rel, tags, lemmas, entities, chunks, odin_id)
        odin_json['documents'][''] = cw.conllu_to_odin([sent], odin_json['documents'][''], False, True)
        
        # add an annotated sample to the list for each trigger on the path
        ann_samples = []
        trigger_toks = search_triggers(sample_['subj_start'], sample_['subj_end'] + 1, sample_['obj_start'], sample_['obj_end'] + 1, rel, tokens) if use_triggers else [None]
        for trigger_tok in trigger_toks:
            ann_samples.append(AnnotatedSample(
                " ".join(tokens), " ".join(tokens), rel, sample_['subj_type'].title(), sample_['obj_type'].title(), tokens, tags, entities, chunks, lemmas,
                (sample_['subj_start'], sample_['subj_end'] + 1), (sample_['obj_start'], sample_['obj_end'] + 1), trigger_tok, g, mdg))
        
        return ann_samples, odin_json


def main_annotate(strategies, dataset, ablation=""):
    print("started loading tacred %s" % dataset)
    # load tacred's dev/test data (we dont need to annotate the train here, because the generation process takes care of that)
    with open("dataset/tacred/data/json/{}.json".format(dataset)) as f:
        data = json.load(f)
    print("finished loading tacred %s" % dataset)
    
    # for each stratagy annotate each sample of the dataset
    for i, (strat_name, enhance_ud, enhanced_plus_plus, enhanced_bart, convs, remove_eud_info, remove_extra_info) in enumerate(strategies):
        start = time.time()
        print("Started annotating %s/l" % strat_name)
        for j, sample in enumerate(data):
            filename = "resources/datasets/tacred-{}-labeled-BART-{}/ann/sent_{:0>5}.json".format(dataset, strat_name, j)
            filename_l = "resources/datasets/tacred-{}-labeled-BART-{}l/ann/sent_{:0>5}.json".format(dataset, strat_name, j)
            try:
                os.makedirs(os.path.dirname(filename))
                os.makedirs(os.path.dirname(filename_l))
            except OSError as exc:  # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise
            
            # annotate current sample
            _, odin_json = SampleBARTAnnotator.annotate_sample(
                sample, sample['relation'].replace('/', '_'), enhance_ud, enhanced_plus_plus, enhanced_bart, convs, remove_eud_info, remove_extra_info, odin_id=j, ablation=ablation)
            
            # dump the annotated sample in its oding format
            with open(filename, 'w') as f:
                json.dump(odin_json['documents'][''], f)
            with open(filename_l, 'w') as f:
                json.dump(odin_json['documents'][''], f)
        print("finished annotating %s/l, time:%.3f" % (strat_name, time.time() - start))


######################################### Generation #########################################


def get_triggers(rel):
    try:
        # NOTE: not sure its the best choise of encoding, but it worked for me
        with open(g_triggers + rel + ".xml", "r", encoding="windows-1252") as f:
            triggers = [l.strip() for l in f.readlines() if l.strip() != '']
        return triggers
    except FileNotFoundError:
        return []


def filter_misparsed_patterns(pattern_dict, str_rel, d):
    new_pattern_dict = dict()
    rel = Relation.fetch(id=str_rel)
    for p, samples in pattern_dict.items():
        try:
            # checks that it is possible to compile a pattern (to prevent it from failing at matching/evaluating time)
            _ = compile_to_odinson_rule(spike_compiler.from_text("\n".join([p]), rel)[0][0])
            new_pattern_dict[p] = samples
        except:
            d.append((str_rel, len(samples), p))
            continue
    return new_pattern_dict


def generate_patterns(data: List, enhance_ud: bool, enhanced_plus_plus: bool, enhanced_bart: bool, convs: int, remove_eud_info: bool, remove_extra_info: bool, use_triggers: bool, ablation: str):
    # first annotate all samples
    ann_samples = defaultdict(list)
    for i, sample in enumerate(data):
        if (i + 1) % 6800 == 0:
            print("finished %d/%d samples" % (i, len(data)))
        
        # store only relations that are subscribed under spike/server/resources/files_db/relations
        #   and notice to store the correct information (cammel case, correct name/label/id etc)
        rel = sample['relation'].replace('/', '_')
        if rel not in spike_relations:
            continue
        
        # annotate
        new_ann_samples, _ = SampleBARTAnnotator.annotate_sample(sample, rel, enhance_ud, enhanced_plus_plus, enhanced_bart, convs, remove_eud_info, remove_extra_info, use_triggers=use_triggers, ablation=ablation)
        
        # store the annotated samples per their relation type
        _ = [ann_samples[ann_sample.relation].append(ann_sample) for ann_sample in new_ann_samples]
    
    pattern_dict_no_lemma = dict()
    pattern_dict_with_lemma = dict()
    # per generation option (w/o lemma)
    for node_selector, pattern_dict in [(WordNodeSelector, pattern_dict_no_lemma), (LemmaNodeSelector, pattern_dict_with_lemma)]:
        total_d = 0
        errs = []
        # per annotated sample
        for rel, ann_samples_per_rel in ann_samples.items():
            triggers = get_triggers(rel)
            
            # instanciate generators and then generate patters
            pattern_generator_with_trigger = PatternGenerator([TriggerVarNodeSelector(triggers)], LabelEdgeSelector(), [])
            pattern_generator_no_trigger = PatternGenerator([], LabelEdgeSelector(), [node_selector()])
            pattern_dict_pre_filter, d = GenerationFromAnnotatedSamples.gen_pattern_dict(ann_samples_per_rel, pattern_generator_with_trigger, pattern_generator_no_trigger)
            
            # filter  misparsed patterns
            pattern_dict[rel] = filter_misparsed_patterns(pattern_dict_pre_filter, rel, errs)
            
            total_d += sum(d.values())
        
        print("%d/%d patterns can’t be created for %s" % (total_d, sum([len(a) for a in ann_samples.values()]), str(node_selector)))
        for err in errs:
            print(err)
    return pattern_dict_no_lemma, pattern_dict_with_lemma


def main_generate(strats, use_triggers, ablation=""):
    print("started loading tacred train")
    # load the training dataset
    with open("dataset/tacred/data/json/train.json") as f:
        train = json.load(f)
    print("finished loading tacred train")
    
    # for each stratagy
    for i, (name, enhance_ud, enhanced_plus_plus, enhanced_bart, convs, remove_eud_info, remove_extra_info) in enumerate(strats):
        print("started generating patterns for strategy %s" % name)
        start = time.time()
        
        # generate patterns
        pattern_dict_no_lemma, pattern_dict_with_lemma = \
            generate_patterns(train, enhance_ud, enhanced_plus_plus, enhanced_bart, convs, remove_eud_info, remove_extra_info, use_triggers, ablation=ablation)
        
        # dump the generated patterns
        print("finished generating patterns for strategy %s/l, strategy-index: %d, time: %.3f" % (name, i, time.time() - start))
        with open("pattern_dicts/pattern_dict_%s%s.pkl" % (name, "" if use_triggers else "_no_trig"), "wb") as f:
            pickle.dump(pattern_dict_no_lemma, f)
        with open("pattern_dicts/pattern_dict_%sl%s.pkl" % (name, "" if use_triggers else "_no_trig"), "wb") as f:
            pickle.dump(pattern_dict_with_lemma, f)


######################################### Evaluation #########################################


# connection to odinson wrapper (see Spike)
def get_link(in_port):
    host = os.environ.get("ODINSON_WRAPPER_HOST", "localhost")
    port = os.environ.get("ODINSON_WRAPPER_PORT", in_port)
    return f"http://{host}:{port}"


def eval_patterns_on_dataset(rel_to_pattern_dict, data_name, in_port, f, is_dev_tuned):
    tot_retrieved_and_relevant = 0
    tot_relevant = 0
    tot_retrieved = 0
    stats_list = dict()
    macro_f = 0
    i = 0
    dev_tuned = dict()
    
    # per relation type in tacred
    for str_rel, patterns in rel_to_pattern_dict.items():
        # originally Spike didn't handle all relations in tacred. Should be fixed by now but just in case:
        if str_rel not in spike_relations:
            continue
        
        # evaluate
        rel = Relation.fetch(id=str_rel)
        e, labels = eval.evaluate_relation(FileBasedDataSet(data_name), spike_compiler.from_text("\n".join(patterns.keys()), rel)[0],
            rel, get_link(in_port), get_link(in_port + 90), compute_global=is_dev_tuned, compute_per_pattern=not is_dev_tuned)
        dev_tuned[str_rel] = labels
        
        # update metrices
        stats = e.get_global_stats()
        tot_retrieved_and_relevant += stats['retrievedAndRelevant']
        tot_retrieved += stats['retrieved']
        tot_relevant += stats['relevant']
        macro_f += stats['f1']
        stats_list[str_rel] = stats
        i += 1
        print("finished rel: %s %d/%d" % (str_rel, i, len(spike_relations)))
    
    # filtering patterns if dev test, for later using against test set
    if not is_dev_tuned:
        for str_rel, patterns in rel_to_pattern_dict.items():
            _ = [patterns.pop(pat) for pat in list(patterns.keys()) if pat not in dev_tuned[str_rel]]
    
    # calculate final metrices, and store them
    prec = (tot_retrieved_and_relevant / tot_retrieved) if tot_retrieved > 0 else 0
    recall = (tot_retrieved_and_relevant / tot_relevant) if tot_relevant > 0 else 0
    micro_f = ((2 * prec * recall) / (prec + recall)) if (prec + recall) > 0 else 0
    macro_f /= len(stats_list)
    json.dump({'p': prec, 'r': recall, 'f1': micro_f, 'ret': tot_retrieved, 'rel': tot_relevant, 'rnr': tot_retrieved_and_relevant}, f)
    return (prec, recall, micro_f, macro_f), stats_list


def main_eval(strats, data, use_lemma, use_triggers, in_port, output_file_path):
    evals = dict()
    
    # We take the patterns that were generated from train, evaluate on dev, filter them,
    #   and write the filtered to a new file for evaluation on test.
    use_tuned = data == 'test'
    dev_tuned_str = "_dev_tuned" if use_tuned else ""
    
    for i, (name, enhance_ud, enhanced_plus_plus, enhanced_bart, convs, remove_eud_info, remove_extra_info) in enumerate(strats):
        # establish the current stratagy, plus extra configuration, such as either using lemmas of words on the path,
        #   and either using triggers.
        name = name + ('l' if use_lemma else '')
        trig_str = "" if use_triggers else "_no_trig"
        
        start = time.time()
        # load the patterns, either train or filtered by dev.
        with open("pattern_dicts/pattern_dict_%s%s%s.pkl" % (name, trig_str, dev_tuned_str), "rb") as f:
            print("started loading patterns for strategy %s" % name)
            pattern_dict = pickle.load(f)
            print("finished loading patterns for strategy %s" % name)
        print("started calculating {}-set scores for strategy {}, trigs: {}".format(data, name, trig_str))
        ff = open(output_file_path if output_file_path else "logs/log_scores_{}_{}_{}.json".format(data, name, trig_str), "w")
        try:
            # evaluate and store in the results dictionary
            evals[(name, data, trig_str)] = eval_patterns_on_dataset(pattern_dict, "tacred-{}-labeled-BART-{}".format(data, name), in_port, ff, dev_tuned)[0]
        except ConnectionError as e:
            raise e
        # best effort
        except Exception as e2:
            print(e2)
            ff.close()
            continue
        if not use_tuned:
            # in this case, we want to store the filtered patterns in a new file, for evaluating on test later.
            with open("pattern_dicts/pattern_dict_%s%s_dev_tuned.pkl" % (name, trig_str), "wb") as f:
                pickle.dump(pattern_dict, f)
        print("finished calculating %s-set scores for strategy %s, %s time: %.3f" % (data, name, trig_str, time.time() - start))
        print("\tscores: " + str(evals[(name, data, trig_str)]))
        ff.close()
    print(str(evals))


######################################### Main #########################################


if __name__ == "__main__":
    # These are the various stratagy-combinations that we've tested, the first is simply UD,
    # then the next two are Stanford's enhanced UD, and the remaining are our BART with different configurations
    strategies = [
        ("n", False, False, False, 1, False, False),        # no enhancing
        ("e", True, True, False, 1, False, False),          # eUD
        ("e2", True, True, False, 1, True, True),           # eUD + no-extra-info-on-label
        ("a", True, True, True, 1, True, True),             # BART's enhancement + eUD
        ("a2", False, False, True, 1, True, True),          # BART's enhancement + no eUD
        ("a3", True, True, True, 2, False, True),           # BART's enhancement
        ("ar", True, True, True, 2, True, True),            # BART's enhancement + eUD + 2 convs
        ("a2r", False, False, True, 2, True, True),         # BART's enhancement + no eUD + 2 convs
        ("a3r", True, True, True, 2, False, True),          # BART's enhancement + eUD + 2 convs + no-extra-info
        ("am", True, True, True, MAX_CONVS, True, True)]    # BART's enhancement + eUD + max convs + no-extra-info
    
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-a', '--action', type=str, default='eval')
    arg_parser.add_argument('-d', '--data', type=str, default='dev')
    arg_parser.add_argument('-x', '--strat_start', type=int, default=-1)
    arg_parser.add_argument('-y', '--strat_end', type=int, default=-1)
    arg_parser.add_argument('-p', '--port', type=int, default=9000)
    arg_parser.add_argument('-l', '--use_lemma', type=int, default=1)
    arg_parser.add_argument('-t', '--use_triggers', type=int, default=1)
    arg_parser.add_argument('-o', '--output_file_path', type=str, default=None)
    arg_parser.add_argument('-b', '--ablation', type=int, default=-1)
    arg_parser.add_argument('-r', '--specified_triggers', type=str, default=None)

    args = arg_parser.parse_args()
    
    # what group of stratagies to use
    if args.strat_start >= 0:
        if args.strat_end >= 0:
            strategies = strategies[args.strat_start:args.strat_end]
        else:
            strategies = strategies[args.strat_start:args.strat_start + 1]
    
    # for ablation test, get ablated function name
    ablation = ""
    if args.ablation >= 0:
        ablations = uda_api.get_conversion_names()
        ablation = sorted(list(ablations))[args.ablation]
    
    # if we want to use specific triggers (w/o we use all the triggers under triggers folder)
    if args.specified_triggers:
        g_triggers = args.specified_triggers
    
    # the different actions we take:
    #   annotate: as we need to have annotated dataset for Spike to Index.
    #       After running this command, we need to Index the annotated data using Spike,
    #       only then we should run the 'generate' and 'eval' commands.
    #   generate: as we need to generate patterns (from the train set) 
    #       that would later be attested on the dev and test sets using the 'eval' command
    #   eval: as we want to filter and evaluate the generated patterns on the dev and test sets (respectively).
    #   ablations: a different test, to check each conversions' contribution.
    if args.action == 'annotate':
        main_annotate(strategies, args.data, ablation)
    elif args.action == 'generate':
        main_generate(strategies, args.use_triggers, ablation)
    elif args.action == 'eval':
        main_eval(strategies, args.data, args.use_lemma, args.use_triggers, args.port, args.output_file_path)
    elif args.action == 'ablations':
        print(f'ablation names:\n\tby execution order:\n\t\t{uda_api.get_conversion_names()}\n\n\tby alphabetical order:\n\t\t{sorted(list(uda_api.get_conversion_names()))}')
