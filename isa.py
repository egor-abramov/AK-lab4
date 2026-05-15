import re
from enum import Enum


class Opcode(str, Enum):
    LUI = "lui"
    MV = "mv"
    SW = "sw"
    LW = "lw"
    ADDI = "addi"
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    AND = "and"
    INV = "inv"
    J = "j"
    JR = "jr"
    JZ = "jz"
    DIV = "div"
    MOD = "mod"
    JG = "jg"
    HALT = "halt"

    def __str__(self):
        return self.name


opcode_to_binary = {
    Opcode.LW: 0x0,
    Opcode.SW: 0x1,
    Opcode.LUI: 0x2,
    Opcode.JZ: 0x3,
    Opcode.MV: 0x4,
    Opcode.INV: 0x5,
    Opcode.ADDI: 0x6,
    Opcode.ADD: 0x7,
    Opcode.SUB: 0x8,
    Opcode.MUL: 0x9,
    Opcode.AND: 0xA,
    Opcode.J: 0xB,
    Opcode.JR: 0xC,
    Opcode.HALT: 0xD,
    Opcode.DIV: 0xE,
    Opcode.MOD: 0xF,
    Opcode.JG: 0x10,
}

binary_to_opcode = {
    0x0: Opcode.LW,
    0x1: Opcode.SW,
    0x2: Opcode.LUI,
    0x3: Opcode.JZ,
    0x4: Opcode.MV,
    0x5: Opcode.INV,
    0x6: Opcode.ADDI,
    0x7: Opcode.ADD,
    0x8: Opcode.SUB,
    0x9: Opcode.MUL,
    0xA: Opcode.AND,
    0xB: Opcode.J,
    0xC: Opcode.JR,
    0xD: Opcode.HALT,
    0xE: Opcode.DIV,
    0xF: Opcode.MOD,
    0x10: Opcode.JG,
}


class Register(str, Enum):
    SP = "data stack pointer"
    RP = "return stack pointer"
    X0 = "x0"
    X1 = "x1"
    X2 = "x2"
    X3 = "x3"
    X4 = "x4"
    T0 = "t0"
    T1 = "t1"
    T2 = "t2"
    T3 = "t3"
    T4 = "t4"
    A0 = "a0"
    A1 = "a1"
    A2 = "a2"
    ZERO = "zero"


register_to_binary = {
    Register.X0: 0x0,
    Register.X1: 0x1,
    Register.X2: 0x2,
    Register.X3: 0x3,
    Register.X4: 0x4,
    Register.A0: 0x5,
    Register.A1: 0x6,
    Register.A2: 0x7,
    Register.T0: 0x8,
    Register.T1: 0x9,
    Register.T2: 0xA,
    Register.T3: 0xB,
    Register.T4: 0xC,
    Register.ZERO: 0xD,
    Register.SP: 0xE,
    Register.RP: 0xF,
}

binary_to_register = {
    0x0: Register.X0,
    0x1: Register.X1,
    0x2: Register.X2,
    0x3: Register.X3,
    0x4: Register.X4,
    0x5: Register.A0,
    0x6: Register.A1,
    0x7: Register.A2,
    0x8: Register.T0,
    0x9: Register.T1,
    0xA: Register.T2,
    0xB: Register.T3,
    0xC: Register.T4,
    0xD: Register.ZERO,
    0xE: Register.SP,
    0xF: Register.RP,
}


def to_bytes(program: list[dict[str, any]]) -> bytearray:
    """
    Преобразует машинный код в бинарное представление

    Бинарное представление инструкций:
    ┌─────────────┬─────────┬─────────┬─────────┬─────────────────────────┐
    │   31...27   │ 26...23 │ 22...19 │ 18...15 │ 14                    0 │
    ├─────────────┼─────────┼─────────┼─────────┼─────────────────────────┤
    │    опкод    │   rd    │   rs1   │   rs2   │        imm value        │
    └─────────────┴─────────┴─────────┴─────────┴─────────────────────────┘
    """

    binary_code = bytearray()
    for item in program:
        if item["type"] == "data":
            val = item["value"] & 0xFFFFFFFF
            binary_code.extend(val.to_bytes(4, byteorder="big"))
        else:
            opcode_bin = opcode_to_binary[item["opcode"]]

            rd = register_to_binary[item.get("rd", Register.X0)]
            rs1 = register_to_binary[item.get("rs1", Register.X0)]
            rs2 = register_to_binary[item.get("rs2", Register.X0)]

            opcode = item["opcode"]
            raw_imm = item.get("imm", 0)
            if opcode in (Opcode.LUI, Opcode.J):
                imm = raw_imm & 0xFFFFF
                rs1 = 0
                rs2 = 0
            elif opcode in (Opcode.LW, Opcode.SW, Opcode.JZ, Opcode.JG):
                imm = raw_imm & 0x7FFF
            elif opcode == Opcode.ADDI:
                imm = raw_imm & 0xFFF
            else:
                imm = raw_imm & 0xFFFFF

            instr_val = (opcode_bin & 0x1F) << 27
            instr_val |= rd << 23
            instr_val |= rs1 << 19
            instr_val |= rs2 << 15
            instr_val |= imm

            binary_code.extend(instr_val.to_bytes(4, byteorder="big"))
    return binary_code


def save_hex(target_path: str, program: list[dict[str, any]]):
    """
    Сохраняет транслированый код в формате
    <label> - <address> - <HEXCODE> - <mnemonic>
    """
    if not target_path.endswith(".hex"):
        target_path += ".hex"

    with open(target_path, "w", encoding="utf-8") as f:
        header = (
            f"{'<label>':<25} | {'<address>':>10} | {'<HEXCODE>':>10} | {'<mnemonic>'}"
        )
        f.write(header + "\n")

        for item in program:
            label = item.get("label", "")
            if label.startswith("_"):
                label = ""
            address = item["address"]

            if item["type"] == "data":
                hexcode = hex(item["value"])
                mnemonic = "DATA"
            elif item["type"] == "instruction":
                hexcode = f"0x{opcode_to_binary[item['opcode']]}"
                args = []
                for arg in item["args"]:
                    if isinstance(arg, Register):
                        args.append(arg.name)
                    elif isinstance(arg, dict):
                        args.append(f"{arg['offset']}({arg['reg'].name})")
                    else:
                        args.append(str(arg))
                mnemonic = f"{item['opcode'].name} {', '.join(args)}"
            line = f"{label:<25} | {address:>10} | {hexcode:>10} | {mnemonic}"
            f.write(line + "\n")


def assemble(code: list[str]) -> ([[str, any]], [str, int]):
    current_addr = 0
    lines = []
    label2addr = {}
    addr2label = {}

    for line in code:
        line = line.split("#")[0].strip()
        if not line:
            continue
        if line.endswith(":"):
            label = line[:-1]
            label2addr[label] = current_addr
            if not label.startswith("__"):
                addr2label[current_addr] = label
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
            instr_args = [_parse_arg(p, label2addr) for p in instruction[1:]]

            rd_val, rs1_val, rs2_val, imm_val = Register.X0, Register.X0, Register.X0, 0

            if opcode in (
                Opcode.ADD,
                Opcode.SUB,
                Opcode.MUL,
                Opcode.AND,
                Opcode.DIV,
                Opcode.MOD,
            ):
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
            elif opcode in (Opcode.JZ, Opcode.JG):
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
            if isinstance(parsed_instruction["imm"], Register):
                print(parsed_instruction)
    return program, label2addr


def _parse_arg(op_str: str, labels: dict[str, int]) -> any:
    op_upper = op_str.upper()
    if op_upper in Register.__members__:
        return Register[op_upper]
    mem_match = re.match(r"^(.*?)\(([a-zA-Z0-9_]+)\)$", op_str)
    if mem_match:
        reg_name = mem_match.group(2).upper()
        if reg_name in Register.__members__:
            offset_str = mem_match.group(1)
            offset_val = _parse_arg(offset_str, labels) if offset_str else 0
            return {"offset": offset_val, "reg": Register[reg_name]}

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
        lo = val & 0xFFF
        if lo & 0x800:
            lo -= 0x1000
        return lo

    if op_str in labels:
        return labels[op_str]
    try:
        return int(op_str, 0)
    except ValueError:
        raise ValueError(f"Unresolvable operand: {op_str}")
