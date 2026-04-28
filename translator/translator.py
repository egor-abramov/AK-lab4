import json
import sys

from _lexer import tokenize, Token
from _kernel import load_kernel

WORD_SIZE = 4
DATA_STACK_INIT_ADDR = 0x6FF
RETURN_STACK_INIT_ADDR = 0x7FF
INPUT_ADDR = 0x5F8
OUTPUT_ADDR = 0x5FC

FORTH_PRIMITIVES = {
    "+": "ADD",
    "-": "SUB",
    "*": "MUL",
    "and": "AND",
    "not": "NOT",
    "dup": "DUP",
    "drop": "DROP",
    "swap": "SWAP",
    "!": "STORE",
    "@": "LOAD",
    "cells": "CELLS",
    "read": "READ",
    ".": "PRINT",
    "=0": "EZ",
    ">0": "GZ",
    "execute": "EXECUTE",
    "print_str": "PRINT_STR",
    "read_str": "READ_STR",
}


class Translator:
    """
    Транслятор Forth в RISC-ассемблер
    Выполняет трансляцию за два прохода:
        1. Расчет адреса статической памяти
        2. Генерация шитого кода
    """

    def __init__(self, kernel_word2addr: dict[str, str], start_addr: int):
        self.word2addr = kernel_word2addr.copy()
        self.var2addr: dict[str, str] = {}

        self.start_addr = start_addr
        self.cur_addr = start_addr
        self.data_addr = 0

        self.code: list[str] = []
        self.data_segment: list[str] = ["Data Segment:"]
        self.loop_stack = []
        self.it = iter([])

        self.last_number = 0

    def _calc_data_addr(self, tokens: list[Token]) -> int:
        """
        Первый проход транслятора.
        Расчет конца сегмента кода для определения адреса начала статической памяти.
        """
        variables = set()
        it = iter(tokens)
        for token in it:
            if token.typ == "WORD":
                if token.value in ["var", "array"]:
                    variables.add(next(it).value)
                elif token.value == "string":
                    next(it)
                    variables.add(next(it).value)

        code_len = 0
        it = iter(tokens)
        for token in it:
            if token.typ == "NUMBER":
                code_len += 2 * WORD_SIZE
            elif token.typ == "STRING":
                code_len += 2 * WORD_SIZE
            elif token.typ == "WORD":
                word = token.value
                if word in ["var", "array"]:
                    next(it)
                elif word == "string":
                    next(it) # skip string token
                    next(it) # skip string name
                elif word == "loop":
                    pass
                elif word in variables or word in ["endloop", "'"]:
                    code_len += 2 * WORD_SIZE
                else:
                    code_len += WORD_SIZE

        return self.start_addr + code_len + WORD_SIZE

    def emit(self, instruction: str):
        self.code.append(instruction)
        self.cur_addr += WORD_SIZE

    def emit_lit(self, value: str):
        self.emit(self.word2addr["LIT"])
        self.emit(str(value))

    def emit_label(self, label: str):
        self.code.append(f"{label}:")

    def translate(self, tokens: list[Token]) -> (list[str], int):
        """
        Проход 2
        Трансляция в шитый код.
        """
        self.data_addr = self._calc_data_addr(tokens)
        self.emit_label("START")

        self.it = iter(tokens)
        for token in self.it:
            if token.typ == "WORD":
                self._translate_word(token.value)
            elif token.typ == "NUMBER":
                self.last_number = token.value
                self.emit_lit(hex(token.value))
            else:
                raise Exception(f"Unexpected token type: {token.typ}")

        self.emit(self.word2addr["HALT"])
        self.code.extend(self.data_segment)
        return self.code, self.data_addr

    def _translate_word(self, word: str):
        if word in FORTH_PRIMITIVES:
            word = FORTH_PRIMITIVES[word]

        if word in self.word2addr:
            self.emit(self.word2addr[word])
        elif word in self.var2addr:
            self.emit_lit(self.var2addr[word])
        elif word == "loop":
            self.loop_stack.append(self.cur_addr)
        elif word == "endloop":
            if not self.loop_stack:
                raise Exception("Syntax error: loop expected")
            target_addr = self.loop_stack.pop()
            self.emit(self.word2addr["JNZ"])
            self.emit(hex(target_addr))
        elif word == ":":
            token_name = str(next(self.it).value)
            self.word2addr[token_name] = hex(self.cur_addr)
            self.emit_label(token_name.upper())
            self.emit("j DOCOL")
        elif word == ";":
            self.emit(self.word2addr["EXIT"])
        elif word == "'":
            target_name = next(self.it).value
            if target_name not in self.word2addr:
                raise Exception(f"Word error: no such word {target_name}")
            target_addr = self.word2addr[target_name]
            self.emit_lit(target_addr)
        elif word == "var":
            var_name = next(self.it).value
            self._assert_free_name(var_name)
            self.var2addr[var_name] = hex(self.data_addr)
            self.data_addr += WORD_SIZE
        elif word == "array":
            arr_name = next(self.it).value
            self._assert_free_name(arr_name)
            self.var2addr[arr_name] = hex(self.data_addr)
            self.data_addr += self.last_number * WORD_SIZE
        elif word == "string":
            str_token = next(self.it)
            if str_token.typ != "STRING":
                raise Exception(f"Syntax error: string literal expected, got {str_token.typ}")

            name_token = next(self.it)
            if name_token.typ != "WORD":
                raise Exception(f"Syntax error: identifier expected, got {name_token.typ}")

            str_name = name_token.value
            self._assert_free_name(str_name)
            self.var2addr[str_name] = hex(self.data_addr)

            str_val = str_token.value
            self.data_segment.append(str(len(str_val)))
            for ch in str_val:
                self.data_segment.append(str(ord(ch)))
            self.data_addr += WORD_SIZE * (len(str_val) + 1)
        else:
            raise Exception(f"Unknown word {word}")

    def _assert_free_name(self, name: str):
        if name in self.var2addr or name in self.word2addr or name in FORTH_PRIMITIVES:
            raise Exception(f"Name error: {name} already defined")


def code2json(asm_lines: list[str]) -> list[dict]:
    json_output = []
    current_address = 0

    for line in asm_lines:
        clean_line = line.strip()
        if not clean_line:
            continue

        if clean_line.endswith(":"):
            row_type = "label"
            json_output.append({
                "address": hex(current_address),
                "type": row_type,
                "value": clean_line
            })
        elif clean_line.startswith("#"):
            continue
        else:
            if clean_line.startswith("0x") or clean_line.lstrip('-').isdigit():
                row_type = "data"
            else:
                row_type = "instruction"
            json_output.append({
                "address": hex(current_address),
                "type": row_type,
                "value": clean_line
            })
            current_address += WORD_SIZE

    return json_output


def main(source_path: str, target_path: str):
    with open(source_path, 'r', encoding="utf-8") as f:
        source_text = f.read()
    INIT_CODE_SIZE = 9 * WORD_SIZE
    addr, kernel_code, start_addr = load_kernel("kernel.s", INIT_CODE_SIZE)
    tokens = tokenize(source_text)

    translator = Translator(addr, start_addr)
    translated_code, data_addr = translator.translate(tokens)

    init_code = [
        "sub x0, x0, x0",
        "sub x1, x1, x1",
        "sub x4, x4, x4",
        "sub sp, sp, sp",
        "sub rp, rp, rp",

        f"addi sp, sp, {DATA_STACK_INIT_ADDR}",
        f"addi rp, rp, {RETURN_STACK_INIT_ADDR}",
        f"addi x0, x0, {start_addr}",
        f"addi x4, x4, {data_addr}",
    ]
    asm = init_code + kernel_code + translated_code

    if "." in target_path:
        target_json_path = target_path.rsplit(".", 1)[0] + ".json"
    else:
        target_json_path = target_path + ".json"

    json_data = code2json(asm)

    with open(target_json_path, 'w', encoding="utf-8") as f:
        f.write("[\n")
        lines = [f"    {json.dumps(item, ensure_ascii=False)}" for item in json_data]
        f.write(",\n".join(lines))
        f.write("\n]\n")


if __name__ == "__main__":
    source = "../examples/in/input.ft"
    target = "../examples/out/out.json"
    main(source, target)
