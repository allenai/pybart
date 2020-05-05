<div align="center">
    <br>
    <img src="logo.png" width="400"/>
    <p>
   A Python converter from Universal-Dependencies trees to <b>BART</b> representation.<br>
        Try out our UD-BART comparison <a href="http://nlp.biu.ac.il/~aryeht/eud/">Demo</a>
    </p>
    <hr/>
</div>
<br/>

BART (**B**ar-Ilan & **A**I2 **R**epresentation **T**ransformation) is our new and cool enhanced-syntatic-representation specialized to improve Relation Extraction, but suitable for any NLP down-stream task.

See our [pyBART: Evidence-based Syntactic Transformations for IE](http://arxiv.org/abs/2005.01306) for detailed description of BART's creation/linguisical-verification/evaluation processes, and list of conversions.

This project is part of a wider project series, related to BART:
1. [**Converter:**](#converter-description) The current project.
2. [**Model:**](https://github.com/allenai/ud_spacy_model) UD based [spaCy](https://spacy.io/) model (pip install [the_large_model](https://storage.googleapis.com/en_ud_model/en_ud_model_lg-1.1.0.tar.gz)). This model is needed when using the converter as a spaCy pipeline component (as spaCy doesn't provide UD-format based models).
3. [**Demo:**](http://nlp.biu.ac.il/~aryeht/eud/) Web-demo making use of the converter, to compare between UD and BART representations.

## Table of contents

- [Converter description](#converter-description)
- [Conversion list](#conversion-list)
- [Installation](#installation)
- [Usage](#usage)
  * [spaCy pipeline component](#spacy-pipeline-component)
  * [CoNLL-U format](#conll-u-format)
- [Configuration](#configuration)
- [Citing](#citing)
- [Team](#team)

<small><i><a href='http://ecotrust-canada.github.io/markdown-toc/'>Table of contents generated with markdown-toc</a></i></small>

## Converter description

 * Converts UD (v1.4) to BART. 
 * Supports Conll-U format, spaCy docs, and spaCy pipeline component (see [Usage](#usage)).
 * Highly configurable (see [Configuration](#configuration)).

**Note:** The BART representation subsumes Stanford's EnhancedUD conversions, these conversions are described [here](http://www.lrec-conf.org/proceedings/lrec2016/pdf/779_Paper.pdf), and were already implemented by [core-NLP Java converter](https://nlp.stanford.edu/software/stanford-dependencies.shtml). As such they were not avialable to python users and thus we have ported them to pyBART and tried to maintain their behavior as much as reasonable.

## Conversion list

<details><summary>Click here if you wish to see the list of covered conversions (TBD: really needs to be updated!)</summary>
<p>

<table>
    <tr>
        <td></td>
        <td>[paper](https://nlp.stanford.edu/pubs/schuster2016enhanced.pdf)   (or [here](http://www.lrec-conf.org/proceedings/lrec2016/pdf/779_Paper.pdf))</td>
        <td>[UD formal guidelines   (v2)](https://universaldependencies.org/u/overview/enhanced-syntax.html)</td>
        <td>coreNLP   code</td>
        <td>Converter</td>
        <td>notes</td>
    </tr>
    <tr>
        <td>nmod/acl/advcl   case info</td>
        <td>eUD</td>
        <td>eUD   (under 'obl' for v2)</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>1.   Even though multi-word prepositions are processed only under eUD++, it is   still handled under eUD to add it in the case information.&lt;br&gt;2. Lowercased (and not lemmatized - important for MWP)</td>
    </tr>
    <tr>
        <td>Passive   agent</td>
        <td>-</td>
        <td>-</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>Only   if the nmod both has a "by" son and has an 'auxpass' sibling, then   instead of nmod:by we fix to nmod:agent</td>
    </tr>
    <tr>
        <td>conj   case info</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>1.   Adds the type of conjunction to all conjunct relations&lt;br&gt;2. Some multi-word coordination markers are collapsed to conj:and or   conj:negcc</td>
    </tr>
    <tr>
        <td>Process   Multi-word prepositions</td>
        <td>eUD++</td>
        <td>eUD   (?)</td>
        <td>eUD++</td>
        <td>eUD++</td>
        <td>Predetermined   lists of 2w and 3w preps.</td>
    </tr>
    <tr>
        <td>Demote   quantificational modifiers (A.K.A Partitives and light noun constructions)</td>
        <td>eUD++</td>
        <td>(see   [here](https://universaldependencies.org/u/overview/enhanced-syntax.html#additional-enhancements))</td>
        <td>eUD++</td>
        <td>eUD++</td>
        <td>Predetermined   list of the quantifier or light noun.</td>
    </tr>
    <tr>
        <td>Conjoined   prepositions and prepositional phrases</td>
        <td>eUD++</td>
        <td>-</td>
        <td>eUD++</td>
        <td>eUD++</td>
        <td></td>
    </tr>
    <tr>
        <td>Propagated   governors and dependents</td>
        <td>eUD   (A, B, C)</td>
        <td>eUD   (A, B, C, D)</td>
        <td>eUD   (A, B, C)</td>
        <td>eUD   (A, B, C)</td>
        <td>1.   This includes: (A) conjoined noun phrases, (B) conjoined adjectival phrases,   (C) subjects of conjoined verbs, and (D) objects of conjoined verbs.&lt;br&gt;2. Notice (D) is relevant to be added theoretically but was omitted for   practical uncertainty (see 4.2 at the paper).</td>
    </tr>
    <tr>
        <td>Subjects   of controlled verbs</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>eUD</td>
        <td>1.   Includes the special case of 'to' with no following verb ("he decided   not to").&lt;br&gt;2. Heuristic for choosing the propagated subject (according to coreNLP   docu): if the control verb has an object it is propagated as the subject of   the controlled verb, otherwise they use the subject of the control verb.</td>
    </tr>
    <tr>
        <td>Subjects   of controlled verbs - when 'to' marker is missing</td>
        <td>?</td>
        <td>?</td>
        <td>-</td>
        <td>extra</td>
        <td>1.   Example: "I started reading the book"&lt;br&gt;2. For some reason not included in the coreNLP code, unsure why</td>
    </tr>
    <tr>
        <td>Relative   pronouns</td>
        <td>eUD++</td>
        <td>eUD   (?)</td>
        <td>eUD++</td>
        <td>eUD++</td>
        <td></td>
    </tr>
    <tr>
        <td>Reduced   relative clause</td>
        <td>-</td>
        <td>eUD   (?)</td>
        <td>-</td>
        <td>extra</td>
        <td></td>
    </tr>
    <tr>
        <td>Subjects   of adverbial clauses</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Heuristic   for choosing the propagated entity:&lt;br&gt;1. If the marker is "to", the object (if it is animated - but for   now we don’t enforce it) of the main clause is propagated as subject,   otherwise the subject of the main clause is propagated.&lt;br&gt;2. Else, if the marker is not one of "as/so/when/if" (this   includes no marker at all which is mostly equivalent to "while"   marker), both the subject and the object of the main clause are equivalent   options (unless no object found, then the subject is propagated).</td>
    </tr>
    <tr>
        <td>Noun-modifying   participles</td>
        <td>(see   [here](https://www.aclweb.org/anthology/W17-6507))</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td></td>
    </tr>
    <tr>
        <td>Correct   possible subject of Noun-modifying participles</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>1.   This is a correctness of the subject decision of the previous bullet.&lt;br&gt;2. If the noun being modified is an object/modifier of a verb with some   subject, then that subject might be the subject of the Noun-modifying   participle as well. (it is uncertain, and seems to be correct only for the   more abstract nouns, but that’s just a first impression).</td>
    </tr>
    <tr>
        <td>Propagated   modifiers (in conjunction constructions)</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Heuristics and assumptions:&lt;br&gt;1. Modifiers that appear after both parts of the conjunction may (the ratio   should be researched) refer to both parts. Moreover, If the modifiers father   is not the immediate conjunction part, then all the conjunction parts between   the father and the modifier are (most probably) modified by the   modifier.&lt;br&gt;2. If the modifier father is the immediate conjunction part, we propagate   the modifier backward only if the new father, doesn't have any modifiers sons   (this is to restrict a bit the amount of false-positives).&lt;br&gt;3. We don’t propagate modifier forwardly (that is, if the conjunct part   appears after the modifier, we assume they don’t refer).&lt;br&gt;4. Should be tested for cost/effectiveness as it may bring many   false-positives.</td>
    </tr>
    <tr>
        <td>Locative   and temporal adverbial modifier propagation (indexicals)</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>1.   Rational: If a locative or temporal adverbial modifier is stretched away from   the verb through a subject/object/modifier(nmod) it should be applied as well   to the verb itself.&lt;br&gt;2. Example: "He was running around, in these woods here".</td>
    </tr>
    <tr>
        <td>Subject   propagation of 'dep'</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Rational:   'dep' is already problematic, as the parser didn't know what relation to   assign it.     In case the secondary clause doesn't have a subject, most probably it   should come from the main clause. It is probably an advcl/conj/parataxis/or   so that was missing some marker/cc/punctuation/etc.</td>
    </tr>
    <tr>
        <td>Apposition   propagation</td>
        <td>(see   [here](https://arxiv.org/pdf/1603.01648.pdf))</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td></td>
    </tr>
    <tr>
        <td>nmod propagation through subj/obj/nmod</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>For now we propagate only modifiers cased by 'like' or 'such_as' prepositions (As they imply reflexivity), and we copy their heads' relation (that is, obj for obj subj for subj and nmod for nmod with its corresponding case).</td>
    </tr>
    <tr>
        <td>possessive</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Share possessive modifiers through conjunctions (e.g. My father and mother went home -&gt; My father and (my) mother...</td>
    </tr>
    <tr>
        <td>Expanding multi word prepositions</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Add an nmod relation when advmod+nmod is observed while concatinating the advmod and preposition to be the new modifiers preposition (this expands the closed set of eUD's 'Process Multi-word preposition').</td>
    </tr>
    <tr>
        <td>Active-passive   alteration</td>
        <td>(see   [here](https://www.aclweb.org/anthology/W17-6507))</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Invert subject and object of passive construction (while keeping the old ones).</td>
    </tr>
    <tr>
        <td>Copula   alteration</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Add   a verb placeholder, reconstruct the tree as if the verb was there.</td>
    </tr>
    <tr>
        <td>Hyphen   alteration</td>
        <td>-</td>
        <td>-</td>
        <td>-</td>
        <td>extra</td>
        <td>Add subject and modifier relations to the verb in the middle of an noun-verb adjectival modifing another noun (e.g. a Miami-based company).</td>
    </tr>
</table>
</p>
</details>

## Installation

pyBART requires Python 3.7 or later. The preferred way to install pyBART is via `pip`. Just run `pip install pybart-nlp` in your Python environment and you're good to go!

   ```bash
   pip install pybart-nlp
   ```

## Usage

Once you've installed pyBART, you can use the package in one of the following ways.
Notice that for both methods we placed '...' (three dots) in the API calls, as we provide a list of optinal parameters to configure the conversion process. We will elaborate about it next.

### spaCy pipeline component

```
# Load a UD-based english model
nlp = spacy.load("en_ud_model")

# Add BART converter to spaCy's pipeline
from pybart-nlp.api import Converter
converter = Converter( ... )
nlp.add_pipe(converter, name="BART")

# Test the new converter component
doc = nlp("He saw me while driving")
me_token = doc[2]
for par_tok in me_token._.parent_list:
    print(par_tok)

# Output:
{'head': 2, 'rel':'dobj', 'src':'UD'}
{'head': 5, 'rel': 'nsubj',
  'src':('advcl','while'), 'alt':'0'}
```

### CoNLL-U format

```
from pybart-nlp.api import convert_bart_conllu

# read a CoNLL-U formatted file
with open(conllu_formatted_file_in) as f:
  sents = f.read()

# convert
converted = convert_bart_conllu(sents, ...)

# use it, probably wanting to write the textual output to a new file
with open(conllu_formatted_file_out, "w") as f:
  f.write(converted)
```

## Configuration

Each of our API calls can get the following optional parameters:

[//]: # (<style>.tablelines table, .tablelines td, .tablelines th {border: 1px solid black;}</style>)



| Name | Type | Default | Explanation |
|------|------|-------------|----|
| enhance_ud | boolean | True | Include Stanford's EnhancedUD conversions. |
| enhanced_plus_plus | boolean | True | Include Stanford's EnhancedUD++ conversions. |
| enhanced_extra | boolean | True | Include BART's unique conversions. |
| conv_iterations | int | inf | Stop the (defaultive) behaivor of iterating on the list of conversions after `conv_iterations` iterations, though before reaching convergance (that is, no change in graph when conversion-list is applied). |
| remove_eud_info | boolean | False | Do not include Stanford's EnhancedUD&EnhancedUD++'s extra label information. |
| remove_extra_info | boolean | False | Do not include BART's extra label information. |
| remove_node_adding_conversions | boolean | False | Do not include conversions that might add nodes to the given graph. |
| remove_unc | boolean | False | Do not include conversions that might contain `uncertainty` (see paper for detailed explanation). |
| query_mode | boolean | False | Do not include conversions that add arcs rather than reorder arcs. |
| funcs_to_cancel | ConvsCanceler class | Empty class instantiation | A list of conversions to prevent from occuring by their names. Use `get_conversion_names` for the full conversion name list |

[//]: # ({: .tablelines})

## Citing

If you use pyBART or BART in your research, please cite [pyBART: Evidence-based Syntactic Transformations for IE](http://arxiv.org/abs/2005.01306).

```bibtex
@inproceedings{Tiktinsky2020pyBARTES,
  title={pyBART: Evidence-based Syntactic Transformations for IE},
  author={Aryeh Tiktinsky and Yoav Goldberg and Reut Tsarfaty},
  year={2020}
}
```

## Team

pyBART is an open-source project backed by [the Allen Institute for Artificial Intelligence (AI2)](https://allenai.org/), and by Bar-Ilan University as being part of [my](https://github.com/aryehgigi) thesis under the supervision of Yoav Goldberg.
AI2 is a non-profit institute with the mission to contribute to humanity through high-impact AI research and engineering.
Our team consists of Yoav Goldberg, Reut Tsarfaty and myself. Currently we are the contributors to this project but we will be more than happy for anyone who wants to help, via Issues and PR's.
