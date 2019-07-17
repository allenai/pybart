# UD2UDE

This (badly-named) project includes couple of mini-projects, all related to the main goal of my thesis.
1. **Converter:** python(3.6) converter, aimed to replace core-nlp's Java converter, and with my researched add-ins.
2. **Model:** spaCy trained model based on UD (and PENN converted to UD) dataset.
3. **Demo:** JS and python code, making use of the converter.
4. **spacy2odin:** jsons converter for annotating data using the Model (above) for odin-son indexing.

# Converter
The converter converts UD (v1.4) to enhancedUD, enhancedUD++, and extra-enhancements (discovered as part of my thesis).
It supports Conll-U and Odin formats (and some conversions between them)

The converter coveres the following conversions:
TODO: continue and elaborate->
1. enhancedUD(++): generally, I maintained the same behavior (mentioned [here](https://universaldependencies.org/u/overview/enhanced-syntax.html)) that was implemented by [core-NLP java converter](https://nlp.stanford.edu/software/stanford-dependencies.shtml) as much as reasonable.
   - Null nodes for elided predicates
   - Propagation of conjuncts
   - Additional subject relations for control and raising constructions
   - Coreference in relative clause constructions
   - Modifier labels that contain the preposition or other case-marking information
2. Extra enhancments
   - TODO
