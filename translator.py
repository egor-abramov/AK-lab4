import argparse
import re

from isa import assemble, to_bytes, save_hex

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
        ("IMPORT", r"import\s+(\w+)+"),
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
        elif typ == "IMPORT":
            lib_name = str(value.split()[1]).lower()
            tokens.append(Token(typ, lib_name))
    return tokens


class Translator:
    def __init__(self):
        self.var2addr: dict[str, str] = {}
        self.word2addr: dict[str, int] = {}

        self.cur_addr = 0
        self.code = []
        self.data_segment = []
        self.loop_stack = []
        self.if_stack = []
        self.func_skips = []
        self.last_number = 0

        self.tokens = []
        self.token_idx = 0

    def emit(self, instruction: str):
        self.code.append(instruction)
        self.cur_addr += WORD_SIZE

    def emit_label(self, label: str):
        self.code.append(f"{label}:")

    def emit_lit(self, val):
        self.emit("addi sp, sp, -4")
        self.emit("sw t1, 0(sp)")
        self.emit("mv t1, t0")
        self.emit_load_imm("t0", val)

    def emit_load_imm(self, reg: str, val):
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
        ret_label = f"_RET_{self.cur_addr}"
        self.emit_load_imm("t2", ret_label)
        self.emit("addi rp, rp, -4")
        self.emit("sw t2, 0(rp)")
        self.emit(f"j {target_label}")
        self.emit_label(ret_label)

    def emit_ret(self):
        self.emit("lw t2, 0(rp)")
        self.emit("addi rp, rp, 4")
        self.emit("jr t2")

    def translate(self, stdlib_tokens: [Token], user_tokens: [Token]) -> [str]:
        self.emit_load_imm("sp", DATA_STACK_INIT_ADDR)
        self.emit_load_imm("rp", RETURN_STACK_INIT_ADDR)

        self.tokens = stdlib_tokens
        self.emit_label("__STDLIB_CODE__")
        self._translate_loop()
        stdlib_data = self.data_segment
        self.data_segment = []

        self.tokens = user_tokens
        self.emit_label("__USER_CODE__")
        self.token_idx = 0
        self._translate_loop()
        user_data = self.data_segment
        self.data_segment = []
        self.emit("halt")

        self.emit_label("__STDLIB_DATA__")
        self.code.extend(stdlib_data)
        self.emit_label("__USER_DATA__")
        self.code.extend(user_data)
        return self.code

    def _translate_loop(self):
        while self.token_idx < len(self.tokens):
            token = self.tokens[self.token_idx]
            is_success = self._peephole(token)
            if is_success:
                continue

            if token.typ == "WORD":
                self._translate_word(token.value)
            elif token.typ == "NUMBER":
                self.last_number = token.value
                self.emit_lit(token.value)
            self.token_idx += 1

    def _peephole(self, token: Token):
        ops = {
            "+": "add",
            "-": "sub",
            "*": "mul",
            "/": "div",
            "div": "div",
            "%": "mod",
            "mod": "mod",
            "and": "and",
        }
        # <num> <operation>
        if (
            token.typ == "NUMBER"
            and self.token_idx + 1 < len(self.tokens)
            and self.tokens[self.token_idx + 1].value in ops
        ):
            val = token.value
            op = ops[self.tokens[self.token_idx + 1].value]
            if op in ["add", "sub"] and -2048 <= val <= 2047:
                self.emit(f"addi t0, t0, {val if op == 'add' else -val}")
            else:
                self.emit_load_imm("t2", val)
                self.emit(f"{op} t0, t0, t2")
            self.token_idx += 2
            return True
        # <var> @
        elif (
            token.typ == "WORD"
            and token.value in self.var2addr
            and self.token_idx + 1 < len(self.tokens)
            and self.tokens[self.token_idx + 1].value == "@"
        ):
            addr = self.var2addr[token.value]
            self.emit("addi sp, sp, -4")
            self.emit("sw t1, 0(sp)")
            self.emit("mv t1, t0")
            self.emit(f"lui t0, %hi({addr})")
            self.emit(f"lw t0, %lo({addr})(t0)")
            self.token_idx += 2
            return True
        # <var> !
        elif (
            token.typ == "WORD"
            and token in self.var2addr
            and self.token_idx + 1 < len(self.tokens)
            and self.tokens[self.token_idx + 1].value == "!"
        ):
            addr = self.var2addr[token.value]
            self.emit(f"lui t2, %hi({addr})")
            self.emit(f"sw t0, %lo({addr})(t2)")

            self.emit("mv t0, t1")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.token_idx += 2
            return True
        return False

    def _translate_word(self, word: str):
        if word == "+":
            self.emit("add t0, t1, t0")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
        elif word == "-":
            self.emit("sub t0, t1, t0")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
        elif word == "*":
            self.emit("mul t0, t1, t0")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
        elif word == "/":
            self.emit("div t0, t1, t0")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
        elif word == "%":
            self.emit("mod t0, t1, t0")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
        elif word == "and":
            self.emit("and t0, t1, t0")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
        elif word == "not":
            self.emit("inv t0, t0")
        elif word == "dup":
            self.emit("addi sp, sp, -4")
            self.emit("sw t1, 0(sp)")
            self.emit("mv t1, t0")
        elif word == "drop":
            self.emit("mv t0, t1")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
        elif word == "swap":
            self.emit("mv t2, t0")
            self.emit("mv t0, t1")
            self.emit("mv t1, t2")
        elif word == "!":
            self.emit("sw t1, 0(t0)")
            self.emit("lw t0, 0(sp)")
            self.emit("lw t1, 4(sp)")
            self.emit("addi sp, sp, 8")
        elif word == "@":
            self.emit("lw t0, 0(t0)")
        elif word == "read":
            self.emit("addi sp, sp, -4")
            self.emit("sw t1, 0(sp)")
            self.emit("mv t1, t0")
            self.emit_load_imm("t2", INPUT_ADDR)
            self.emit("lw t0, 0(t2)")
        elif word == ".":
            self.emit_load_imm("t2", OUTPUT_ADDR)
            self.emit("sw t0, 0(t2)")
            self.emit("mv t0, t1")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")

        elif word == "loop":
            loop_lbl = f"LOOP_{self.cur_addr}"
            self.loop_stack.append(loop_lbl)
            self.emit_label(loop_lbl)
        elif word == "endloop":
            if not self.loop_stack:
                raise Exception("Syntax error: loop expected")
            loop_start_label = self.loop_stack.pop()
            loop_end_label = f"ENDLOOP_{self.cur_addr}"
            self.emit("mv t2, t0")
            self.emit("mv t0, t1")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit(f"jz t2, {loop_end_label}")
            self.emit(f"j {loop_start_label}")
            self.emit_label(loop_end_label)

        elif word == "if":
            false_label = f"IF_FALSE_{self.cur_addr}"
            self.if_stack.append(("IF", false_label))
            self.emit("mv t2, t0")
            self.emit("mv t0, t1")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
            self.emit(f"jz t2, {false_label}")

        elif word == "else":
            tag, false_label = self.if_stack.pop()
            if tag != "IF":
                raise Exception("ELSE without IF")
            end_label = f"IF_END_{self.cur_addr}"
            self.emit(f"j {end_label}")
            self.emit_label(false_label)
            self.if_stack.append(("ELSE", end_label))

        elif word == "then":
            tag, end_label = self.if_stack.pop()
            if tag != "IF" and tag != "ELSE":
                raise Exception("THEN without IF/ELSE")
            self.emit_label(end_label)

        elif word in ["=0", ">0", "<0"]:
            true_label = f"IS_TRUE_{self.cur_addr}"
            end_label = f"IS_FALSE_{self.cur_addr}"
            self.emit("mv t2, t0")
            self.emit("addi t0, zero, 0")
            if word == "=0":
                self.emit(f"jz t2, {true_label}")
            elif word == ">0":
                self.emit(f"jg t2, {true_label}")
            elif word == "<0":
                self.emit(f"jl t2, {true_label}")

            self.emit(f"j {end_label}")
            self.emit_label(true_label)
            self.emit("addi t0, zero, 1")
            self.emit_label(end_label)
        elif word == ":":
            self.token_idx += 1
            next_t = self.tokens[self.token_idx]
            token_name = str(next_t.value).upper()
            skip_label = f"_SKIP_FUNC_{token_name}"
            self.emit(f"j {skip_label}")
            self.emit_label(token_name)
            self.word2addr[token_name] = self.cur_addr
            self.func_skips.append(skip_label)
        elif word == ";":
            self.emit_ret()
            skip_label = self.func_skips.pop()
            self.emit_label(skip_label)

        elif word == "'":
            self.token_idx += 1
            next_t = self.tokens[self.token_idx]
            target_name = next_t.value.upper()
            self.emit_lit(target_name)

        elif word == "cells":
            self.emit_load_imm("t2", 4)
            self.emit("mul t0, t0, t2")

        elif word == "execute":
            self.emit("mv t2, t0")
            self.emit("mv t0, t1")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
            ret_label = f"_EXEC_RET_{self.cur_addr}"
            self.emit_load_imm("t3", ret_label)
            self.emit("addi rp, rp, -4")
            self.emit("sw t3, 0(rp)")
            self.emit("jr t2")
            self.emit_label(ret_label)

        elif word == "var":
            self.token_idx += 1
            next_t = self.tokens[self.token_idx]
            var_name = next_t.value
            self._assert_free_name(var_name)
            label = f"VAR_{var_name.upper()}"
            self.var2addr[var_name] = label
            self.data_segment.append(f"{label}:")
            self.data_segment.append("0")

        elif word == "array":
            self.token_idx += 1
            next_t = self.tokens[self.token_idx]
            arr_name = next_t.value
            self._assert_free_name(arr_name)
            self.emit("mv t0, t1")
            self.emit("lw t1, 0(sp)")
            self.emit("addi sp, sp, 4")
            label = f"ARR_{arr_name.upper()}"
            self.var2addr[arr_name] = label
            self.data_segment.append(f"{label}:")
            for _ in range(self.last_number):
                self.data_segment.append("0")

        elif word == "string":
            self.token_idx += 1
            next_t = self.tokens[self.token_idx]
            str_val = next_t.value
            self.token_idx += 1
            next_t = self.tokens[self.token_idx]
            str_name = next_t.value
            self._assert_free_name(str_name)
            label = f"STR_{str_name.upper()}"
            self.var2addr[str_name] = label
            self.data_segment.append(f"{label}:")
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


def main(source_path: str, target_path: str):
    with open(source_path, "r", encoding="utf-8") as f:
        source_text = f.read()

    tokens = tokenize(source_text)
    libs = list(map(lambda t: t.value, filter(lambda t: t.typ == "IMPORT", tokens)))
    tokens = list(filter(lambda t: t.typ != "IMPORT", tokens))

    libs_text = []
    for lib in libs:
        with open(f"libs/{lib}.fth", "r", encoding="utf-8") as f:
            libs_text.append(f.read())
    libs_text = "\n".join(libs_text)
    libs_tokens = tokenize(libs_text)

    translator = Translator()
    translated_code = translator.translate(libs_tokens, tokens)
    parsed_program, label2addr = assemble(translated_code)

    user_start = label2addr.get("__USER_CODE__", 0)
    user_data_start = label2addr.get("__USER_DATA__", 0)

    filtered_program = []
    for item in parsed_program:
        addr = item["address"]
        if item["type"] == "data":
            if addr >= user_data_start:
                filtered_program.append(item)
        else:
            if addr >= user_start:
                filtered_program.append(item)
    save_hex(target_path, filtered_program)

    binary_code = to_bytes(parsed_program)
    if not target_path.endswith(".bin"):
        target_path += ".bin"
    with open(target_path, "wb") as f:
        f.write(binary_code)
    print(f"Binary saved to {target_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default="./examples/math/math.fth")
    parser.add_argument("target", nargs="?", default="./examples/math/math.bin")
    args = parser.parse_args()
    main(args.source, args.target)
