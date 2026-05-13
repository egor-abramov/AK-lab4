import argparse
import re

from isa import Opcode, Register, to_bytes, save_hex

WORD_SIZE = 4
DATA_STACK_INIT_ADDR = 0x3F80
RETURN_STACK_INIT_ADDR = 0x4000
INPUT_ADDR = 0x3EF8
OUTPUT_ADDR = 0x3EFC


class Token:
    def __init__(self, typ, value):
        self.typ: str = typ
        self.value = value

    def __repr__(self):
        return f"Token=({self.typ}, {self.value})"


def tokenize(code: str) -> list[Token]:
    tokens: list[Token] = []
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


class Translator:
    def __init__(self):
        self.var2addr: dict[str, str] = {}
        self.word2addr: dict[str, int] = {}

        self.cur_addr = 0
        self.code = []
        self.data_segment = []
        self.loop_stack = []
        self.func_skips = []
        self.it = iter([])
        self.last_number = 0

    def emit(self, instruction: str):
        self.code.append(instruction)
        self.cur_addr += WORD_SIZE

    def emit_label(self, label: str):
        self.code.append(f"{label}:")

    def emit_lit(self, val):
        self.emit_lit_reg("t0", val)
        self.emit("addi sp, sp, -4")
        self.emit("sw t0, 0(sp)")

    def emit_lit_reg(self, reg: str, val):
        if isinstance(val, int):
            if -2048 <= val <= 2047:
                self.emit(f"addi {reg}, zero, {val}")
            else:
                upper = (val >> 12) & 0xFFFFF
                lower = val & 0xFFF
                if lower & 0x800:
                    upper += 1
                self.emit(f"lui {reg}, {upper}")
                self.emit(f"addi {reg}, {reg}, {lower}")
        else:
            self.emit(f"lui {reg}, %hi({val})")
            self.emit(f"addi {reg}, {reg}, %lo({val})")

    def emit_call(self, target_label: str):
        ret_label = f"RET_{self.cur_addr}"
        self.emit_lit_reg("t1", ret_label)
        self.emit("addi rp, rp, -4")
        self.emit("sw t1, 0(rp)")
        self.emit(f"j {target_label}")
        self.emit_label(ret_label)

    def emit_ret(self):
        self.emit("lw t1, 0(rp)")
        self.emit("addi rp, rp, 4")
        self.emit("jr t1")

    def translate(self, tokens: list[Token]) -> list[str]:
        self.emit_lit_reg("sp", DATA_STACK_INIT_ADDR)
        self.emit_lit_reg("rp", RETURN_STACK_INIT_ADDR)

        self.it = iter(tokens)
        for token in self.it:
            if token.typ == "WORD":
                self._translate_word(token.value)
            elif token.typ == "NUMBER":
                self.last_number = token.value
                self.emit_lit(token.value)

        self.emit("halt")

        self.code.extend(self.data_segment)
        return self.code

    def _translate_word(self, word: str):
        if word == "+":
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit("lw t1, 0(sp)")
            self.emit("add t0, t0, t1")
            self.emit("sw t0, 0(sp)")
        elif word == "-":
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit("lw t1, 0(sp)")
            self.emit("sub t0, t1, t0")
            self.emit("sw t0, 0(sp)")
        elif word == "*":
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit("lw t1, 0(sp)")
            self.emit("mul t0, t0, t1")
            self.emit("sw t0, 0(sp)")
        elif word == "and":
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit("lw t1, 0(sp)")
            self.emit("and t0, t0, t1")
            self.emit("sw t0, 0(sp)")
        elif word == "not":
            self.emit("lw t0, 0(sp)")
            self.emit("inv t0, t0")
            self.emit("sw t0, 0(sp)")
        elif word == "dup":
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, -4")
            self.emit("sw t0, 0(sp)")
        elif word == "drop":
            self.emit("addi sp, sp, 4")
        elif word == "swap":
            self.emit("lw t0, 0(sp)")
            self.emit("lw t1, 4(sp)")
            self.emit("sw t0, 4(sp)")
            self.emit("sw t1, 0(sp)")
        elif word == "!":
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit("sw t1, 0(t0)")
        elif word == "@":
            self.emit("lw t0, 0(sp)")
            self.emit("lw t1, 0(t0)")
            self.emit("sw t1, 0(sp)")
        elif word == "read":
            self.emit_lit_reg("t0", INPUT_ADDR)
            self.emit("lw t1, 0(t0)")
            self.emit("addi sp, sp, -4")
            self.emit("sw t1, 0(sp)")
        elif word == ".":
            self.emit_lit_reg("t0", OUTPUT_ADDR)
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit("sw t1, 0(t0)")

        elif word == "loop":
            loop_lbl = f"LOOP_{self.cur_addr}"
            self.loop_stack.append(loop_lbl)
            self.emit_label(loop_lbl)
        elif word == "endloop":
            if not self.loop_stack:
                raise Exception("Syntax error: loop expected")
            loop_start_lbl = self.loop_stack.pop()
            loop_end_lbl = f"ENDLOOP_{self.cur_addr}"
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit(f"jz t0, {loop_end_lbl}")
            self.emit(f"j {loop_start_lbl}")
            self.emit_label(loop_end_lbl)

        elif word == "=0":
            exec_lbl = f"EXEC_{self.cur_addr}"
            skip_lbl = f"SKIP_{self.cur_addr}"
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit(f"jz t0, {exec_lbl}")
            self.emit(f"j {skip_lbl}")
            self.emit_label(exec_lbl)
            next_t = next(self.it)
            if next_t.typ == "NUMBER":
                self.emit_lit(next_t.value)
            else:
                self._translate_word(next_t.value)
            self.emit_label(skip_lbl)

        elif word == ">0":
            exec_lbl = f"EXEC_{self.cur_addr}"
            skip_lbl = f"SKIP_{self.cur_addr}"
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit(f"jz t0, {skip_lbl}")
            self.emit("lui t1, 524288")
            self.emit("and t1, t0, t1")
            self.emit(f"jz t1, {exec_lbl}")
            self.emit(f"j {skip_lbl}")
            self.emit_label(exec_lbl)
            next_t = next(self.it)
            if next_t.typ == "NUMBER":
                self.emit_lit(next_t.value)
            else:
                self._translate_word(next_t.value)
            self.emit_label(skip_lbl)

        elif word == ":":
            token_name = str(next(self.it).value).upper()
            skip_lbl = f"SKIP_FUNC_{token_name}"
            self.emit(f"j {skip_lbl}")
            self.emit_label(token_name)
            self.word2addr[token_name] = self.cur_addr
            self.func_skips.append(skip_lbl)
        elif word == ";":
            self.emit_ret()
            skip_lbl = self.func_skips.pop()
            self.emit_label(skip_lbl)

        elif word == "'":
            target_name = next(self.it).value.upper()
            self.emit_lit(target_name)

        elif word == "cells":
            self.emit("lw t0, 0(sp)")
            self.emit("addi t1, zero, 4")
            self.emit("mul t0, t0, t1")
            self.emit("sw t0, 0(sp)")

        elif word == "execute":
            self.emit("lw t0, 0(sp)")
            self.emit("addi sp, sp, 4")
            ret_lbl = f"EXEC_RET_{self.cur_addr}"
            self.emit(f"addi t1, zero, {ret_lbl}")
            self.emit("addi rp, rp, -4")
            self.emit("sw t1, 0(rp)")
            self.emit("jr t0")
            self.emit_label(ret_lbl)

        elif word == "var":
            var_name = next(self.it).value
            self._assert_free_name(var_name)
            lbl = f"VAR_{var_name.upper()}"
            self.var2addr[var_name] = lbl
            self.data_segment.append(f"{lbl}:")
            self.data_segment.append("0")

        elif word == "array":
            arr_name = next(self.it).value
            self._assert_free_name(arr_name)
            self.emit("addi sp, sp, 4")
            lbl = f"VAR_{arr_name.upper()}"
            self.var2addr[arr_name] = lbl
            self.data_segment.append(f"{lbl}:")
            for _ in range(self.last_number):
                self.data_segment.append("0")

        elif word == "string":
            str_val = next(self.it).value
            str_name = next(self.it).value
            self._assert_free_name(str_name)
            lbl = f"VAR_{str_name.upper()}"
            self.var2addr[str_name] = lbl
            self.data_segment.append(f"{lbl}:")
            self.data_segment.append(str(len(str_val)))
            for ch in str_val:
                self.data_segment.append(str(ord(ch)))
        elif word.upper() in self.word2addr:
            self.emit_call(word.upper())
        elif word in self.var2addr:
            self.emit_lit(self.var2addr[word])
        else:
            raise Exception(f"Unknown word {word}")

    def _assert_free_name(self, name: str):
        if name in self.var2addr or name.upper() in self.word2addr:
            raise Exception(f"Name error: {name} already defined")


def assemble(code: list[str]) -> list[dict[str, any]]:
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
            data_item = {"address": addr, "type": "data", "value": int(line, 0)}
            if addr in addr2label:
                data_item["label"] = addr2label[addr]
            program.append(data_item)
        else:
            instruction = line.replace(",", " ").split()
            mnemonic = instruction[0].upper()
            opcode = Opcode[mnemonic]
            instr_args = [parse_arg(p, label2addr) for p in instruction[1:]]

            rd_val, rs1_val, rs2_val, imm_val = Register.X0, Register.X0, Register.X0, 0

            if opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.AND):
                rd_val, rs1_val, rs2_val = instr_args[0], instr_args[1], instr_args[2]
            elif opcode == Opcode.INV:
                rd_val, rs1_val = instr_args[0], instr_args[1]
            elif opcode == Opcode.ADDI:
                rd_val, rs1_val, imm_val = instr_args[0], instr_args[1], instr_args[2]
            elif opcode == Opcode.LUI:
                rd_val, imm_val = instr_args[0], instr_args[1]
            elif opcode == Opcode.MV:
                rd_val, rs1_val = instr_args[0], instr_args[1]
            elif opcode == Opcode.LW:
                rd_val = instr_args[0]
                rs1_val = instr_args[1]["reg"]
                imm_val = instr_args[1]["offset"]
            elif opcode == Opcode.SW:
                rs2_val = instr_args[0]
                rs1_val = instr_args[1]["reg"]
                imm_val = instr_args[1]["offset"]
            elif opcode == Opcode.J:
                imm_val = instr_args[0]
            elif opcode == Opcode.JR:
                rs1_val = instr_args[0]
            elif opcode == Opcode.JZ:
                rs1_val = instr_args[0]
                imm_val = instr_args[1]

            parsed_instruction = {
                "address": addr,
                "type": "instruction",
                "opcode": opcode,
                "args": instr_args,
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
    op_upper = op_str.upper()
    if op_upper in Register.__members__:
        return Register[op_upper]
    mem_match = re.match(r"^(-?[0-9a-fA-F]+)\(([a-zA-Z0-9_]+)\)$", op_str)
    if mem_match:
        offset = int(mem_match.group(1), 0)
        reg_name = mem_match.group(2).upper()
        return {"offset": offset, "reg": Register[reg_name]}

    if op_str.startswith("%hi("):
        lbl = op_str[4:-1]
        val = labels[lbl]
        lower = val & 0xFFF
        upper = (val >> 12) & 0xFFFFF
        if lower & 0x800:
            upper += 1
        return upper & 0xFFFFF

    if op_str.startswith("%lo("):
        lbl = op_str[4:-1]
        val = labels[lbl]
        return val & 0xFFF

    if op_str in labels:
        return labels[op_str]
    try:
        return int(op_str, 0)
    except ValueError:
        raise ValueError(f"Unresolvable operand: {op_str}")


def main(source_path: str, target_path: str):
    with open("stdlib.fth", "r", encoding="utf-8") as f:
        stdlib_text = f.read()

    with open(source_path, "r", encoding="utf-8") as f:
        source_text = f.read()

    tokens = tokenize(stdlib_text + "\n" + source_text)
    translator = Translator()
    translated_code = translator.translate(tokens)
    parsed_program = assemble(translated_code)
    save_hex(target_path, parsed_program)

    binary_code = to_bytes(parsed_program)
    if not target_path.endswith(".bin"):
        target_path += ".bin"
    with open(target_path, "wb") as f:
        f.write(binary_code)
    print(f"Binary saved to {target_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default="./examples/hello/hello.fth")
    parser.add_argument("target", nargs="?", default="./examples/hello/hello.bin")
    args = parser.parse_args()
    main(args.source, args.target)
