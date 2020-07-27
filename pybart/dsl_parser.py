import os


def parse_rule(lines_of_dsl):
    for line in lines_of_dsl:
        pass
    

def parse_rules(directory):
    rules = []
    for filename in os.listdir(directory):
        if not filename.endswith(".bartdsl"):
            continue
        with open(filename) as f:
            lines = f.readlines()
        rules.append(parse_rule(lines))
    return rules
