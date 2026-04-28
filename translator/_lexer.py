import re


class Token:
    def __init__(self, typ, value):
        self.typ: str = typ
        self.value = value

    def __repr__(self):
        return f"Token=({self.typ}, {self.value})"


def tokenize(code: str) -> [Token]:
    tokens: [Token] = []

    token_specification = [
        ("STRING", r'"[^"]*"'),
        ("NUMBER", r"-?\d+"),
        ("WORD", r"[^\s]+"),
    ]

    token_regexp = "|".join([f"(?P<{pair[0]}>{pair[1]})" for pair in token_specification])
    for m in re.finditer(token_regexp, code):
        typ = m.lastgroup
        value = m.group()
        if typ == "NUMBER":
            tokens.append(Token(typ, int(value)))
        elif typ == "WORD":
            tokens.append(Token(typ, str(value).lower()))
        elif typ == "STRING":
            tokens.append(Token(typ, value[1:-1]))
    return tokens
