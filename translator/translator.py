import json
import re

from isa import Opcode, Register, to_bytes

WORD_SIZE = 4
DATA_STACK_INIT_ADDR = 0x6FF
RETURN_STACK_INIT_ADDR = 0x7FF
INPUT_ADDR = 0x5F8
OUTPUT_ADDR = 0x5FC

# Перевод forth слов в метки kernel.s
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


class Token:
    def __init__(self, typ, value):
        self.typ: str = typ
        self.value = value

    def __repr__(self):
        return f"Token=({self.typ}, {self.value})"


def tokenize(code: str) -> [Token]:
    """
    Исходный код разбивается на токены, для последующей обработки
    """

    tokens: [Token] = []

    token_specification = [
        ("STRING", r'"[^"]*"'),
        ("NUMBER", r"-?\d+"),
        ("WORD", r"[^\s]+"),
    ]

    token_regexp = "|".join(
        [f"(?P<{pair[0]}>{pair[1]})" for pair in token_specification]
    )
    for m in re.finditer(token_regexp, code):
        typ = m.lastgroup
        value = m.group()
        if typ == "NUMBER":
            tokens.append(Token(typ, int(value)))
        elif typ == "WORD":
            tokens.append(Token(typ, str(value).lower()))
        elif typ == "STRING":
            actual_str = value[1:-1].encode("utf-8").decode("unicode_escape")
            tokens.append(Token(typ, actual_str))
    return tokens


def load_kernel(path: str, start_addr: int = 0x0) -> (dict[str, str], [str], hex):
    """
    Загружает код ядра (kernel.s)
    """

    labels = {}
    code = []
    current_addr = start_addr
    label_pattern = re.compile(r"^([A-Z_a-z0-9]*):")
    instruction_pattern = re.compile(r"^([A-Z_a-z]+)")

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue

            label_match = label_pattern.match(line)
            if label_match:
                label_name = label_match.group(1)
                labels[label_name] = hex(current_addr)

                line = line[label_match.end() :].strip()
                code.append(f"{label_name}:")

            if instruction_pattern.match(line):
                current_addr += 4
                code.append(line)

    return labels, code, current_addr


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
        Проход 1.
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
                    next(it)  # skip string token
                    next(it)  # skip string name
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
                raise Exception(
                    f"Syntax error: string literal expected, got {str_token.typ}"
                )

            name_token = next(self.it)
            if name_token.typ != "WORD":
                raise Exception(
                    f"Syntax error: identifier expected, got {name_token.typ}"
                )

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


def assemble(code: list[str]) -> list[dict[str, any]]:
    """
    Переводит строковый код в словари формата
    {
        address: 0,
        type: "instruction" / "data",
        label: "",

        value: 0,                       <- для ячееек с данными

        opcode: isa.Opcode,             <- для ячеек с инструкциями
        args: [],
    }
    """
    current_addr = 0
    lines = []
    label2addr = {}
    addr2label = {}
    for line in code:
        line = line.split("#")[0].strip()
        if not line:
            continue
        if line.endswith(":"):
            label2addr[line[:-1]] = current_addr
            addr2label[current_addr] = line[:-1]
        else:
            lines.append((current_addr, line))
            current_addr += 4

    program: list[dict[str, any]] = []
    for addr, line in lines:
        if line.startswith("0x") or line.lstrip("-").isdigit():
            program.append({"address": addr, "type": "data", "value": int(line, 0)})
        else:
            instruction = line.replace(",", " ").split()
            mnemonic = instruction[0].upper()

            if mnemonic not in Opcode.__members__:
                raise ValueError(f"Unknown opcode: {mnemonic} in line {line}")

            opcode = Opcode[mnemonic]
            args = [parse_arg(p, label2addr) for p in instruction[1:]]
            rd_val, rs1_val, rs2_val, imm_val = (
                Register.X0,
                Register.X0,
                Register.X0,
                0,
            )

            if opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.AND):
                rd_val, rs1_val, rs2_val = args[0], args[1], args[2]
            elif opcode == Opcode.INV:
                rd_val, rs1_val = args[0], args[1]
            elif opcode == Opcode.ADDI:
                rd_val, rs1_val, imm_val = args[0], args[1], args[2]
            elif opcode == Opcode.LUI:
                rd_val, imm_val = args[0], args[1]
            elif opcode == Opcode.MV:
                rd_val, rs1_val = args[0], args[1]
            elif opcode == Opcode.LW:
                rd_val = args[0]
                rs1_val = args[1]["reg"]
                imm_val = args[1]["offset"]
            elif opcode == Opcode.SW:
                rs2_val = args[0]
                rs1_val = args[1]["reg"]
                imm_val = args[1]["offset"]
            elif opcode == Opcode.J:
                imm_val = args[0]
            elif opcode == Opcode.JR:
                rs1_val = args[0]
            elif opcode == Opcode.JZ:
                rs1_val = args[0]
                imm_val = args[1]

            parsed_instruction = {
                "address": addr,
                "type": "instruction",
                "opcode": opcode,
                "args": args,
                "rd": rd_val,
                "rs1": rs1_val,
                "rs2": rs2_val,
                "imm": imm_val,
            }
            if addr in addr2label:
                parsed_instruction["label"] = addr2label[addr]
            program.append(parsed_instruction)
    return program


def parse_arg(op_str: str, labels: dict[str, int]) -> any:
    """
    Разбирает строковый аргумент и возвращает Register, число или словарь смещения.
    """
    op_upper = op_str.upper()

    if op_upper in Register.__members__:
        return Register[op_upper]

    mem_match = re.match(r"^(-?[0-9a-fA-F]+)\(([a-zA-Z0-9_]+)\)$", op_str)
    if mem_match:
        offset = int(mem_match.group(1), 0)
        reg_name = mem_match.group(2).upper()
        if reg_name in Register.__members__:
            return {"offset": offset, "reg": Register[reg_name]}
        else:
            raise ValueError(f"Unknown register in memory operand: {reg_name}")

    if op_str in labels:
        return labels[op_str]

    try:
        return int(op_str, 0)
    except ValueError:
        pass

    raise ValueError(f"Unresolvable operand: {op_str}")


def save_json(target_path: str, program: list[dict[str, any]]):
    """
    Сохраняет транслированый код в json формате для дебага
    """
    json_data = []
    for item in program:
        json_item = {}
        if "label" in item:
            json_item["label"] = item["label"]
        json_item["address"] = hex(item["address"])
        json_item["type"] = item["type"]

        if item["type"] == "data":
            json_item["value"] = hex(item["value"])
        else:
            json_item["opcode"] = item["opcode"].name
            json_item["args"] = []
            for arg in item["args"]:
                if isinstance(arg, Register):
                    json_item["args"].append(arg.name)
                elif isinstance(arg, dict):
                    json_item["args"].append(
                        {"offset": arg["offset"], "reg": arg["reg"].name}
                    )
                else:
                    json_item["args"].append(arg)
        json_data.append(json_item)

    if not target_path.endswith(".json"):
        target_path += ".json"
    with open(target_path, "w") as f:
        f.write("[\n")
        lines = [f"    {json.dumps(item, ensure_ascii=False)}" for item in json_data]
        f.write(",\n".join(lines))
        f.write("\n]\n")


def main(source_path: str, target_path: str):
    with open(source_path, "r", encoding="utf-8") as f:
        source_text = f.read()
    INIT_CODE_SIZE = 3 * WORD_SIZE
    addr, kernel_code, start_addr = load_kernel("kernel.s", INIT_CODE_SIZE)
    tokens = tokenize(source_text)

    translator = Translator(addr, start_addr)
    translated_code, data_addr = translator.translate(tokens)

    init_code = [
        f"addi x0, zero, {start_addr}",
        f"addi sp, zero, {DATA_STACK_INIT_ADDR}",
        f"addi rp, zero, {RETURN_STACK_INIT_ADDR}",
    ]
    asm = init_code + kernel_code + translated_code
    parsed_program = assemble(asm)
    save_json(target_path, parsed_program)

    binary_code = to_bytes(parsed_program)
    if not target_path.endswith(".bin"):
        target_path += ".bin"
    with open(target_path, "wb") as f:
        f.write(binary_code)


# TODO: add hex
# TODO: remove json
if __name__ == "__main__":
    source = "../examples/hello_world/hello_word.ft"
    target = "../examples/hello_world/hello_world.bin"
    main(source, target)
