import json

with open("./eud_literal_allowed_list_en.json") as f:
    en = json.load(f)

with open("./eud_literal_allowed_list_he.json") as f:
    he = json.load(f)

# not sure we need to put these literals as well but to be on the safe sie since they are after `:` we included them
EUD_LITERAL_ALLOWED_LIST = ["cite", "preconj", "qmod", "prt", "predet", "nor", "negcc", "relcl"] + en + he
