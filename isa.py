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
    0xD: Opcode.HALT
}


class Register(str, Enum):
    PC = "program counter"
    SP = "data stack pointer"
    RP = "return stack pointer"
    X0 = "x0"
    X1 = "x1"
    X2 = "x2"
    X3 = "x3"
    X4 = "x4"


register_to_binary = {
    Register.X0: 0x0,
    Register.X1: 0x1,
    Register.X2: 0x2,
    Register.X3: 0x3,
    Register.X4: 0x4,
    Register.PC: 0x5,
    Register.SP: 0x6,
    Register.RP: 0x7,
}

binary_to_register = {
    0x0: Register.X0,
    0x1: Register.X1,
    0x2: Register.X2,
    0x3: Register.X3,
    0x4: Register.X4,
    0x5: Register.PC,
    0x6: Register.SP,
    0x7: Register.RP,
}


class AddrMode(int, Enum):
    REG = 0x0  # регистровая
    IMM = 0x1  # непосредственная загрузка
    IND = 0x2  # косвенная со смещением
    ABS = 0x3  # абсолютная


def to_bytes(code: list[dict[str, any]]) -> bytes:
    """
    Преобразует машинный код в бинарное представление

    Бинарное представление инструкций:
    ┌─────────────────┬─────────┬────────────────────────────────────────────┐
    │     31...26     │  25-23  │ 22                                       0 │
    ├─────────────────┼─────────┼────────────────────────────────────────────┤
    │      опкод      │ реж.адр │                аргуметны                   │
    └─────────────────┴─────────┴────────────────────────────────────────────┘
    """

    binary_bytes = bytearray()
    for item in code:
        if item["type"] == "data":
            binary_bytes.extend(item["value"].to_bytes(4, byteorder='big', signed=True))
        else:
            opcode = item["opcode"]
            args = item["args"]
            op_bits = opcode_to_binary[opcode]
            arg_bits = 0

            # регистровая адресация
            if opcode in (
                    Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.AND, Opcode.MV, Opcode.INV, Opcode.JR, Opcode.HALT):
                mode_bits = AddrMode.REG

                if len(args) > 0:
                    arg_bits |= (register_to_binary[args[0]] & 0x7) << 20
                if len(args) > 1:
                    arg_bits |= (register_to_binary[args[1]] & 0x7) << 17
                if len(args) > 2:
                    arg_bits |= (register_to_binary[args[2]] & 0x7) << 14

            # непосредственная загрузка
            elif opcode in (Opcode.LUI, Opcode.ADDI):
                mode_bits = AddrMode.IMM
                if opcode == Opcode.LUI:
                    rd, k = args[0], args[1]
                    arg_bits |= (register_to_binary[rd] << 20)
                    arg_bits |= (k & 0xFFFFF)
                elif opcode == Opcode.ADDI:
                    rd, rs, k = args[0], args[1], args[2]
                    arg_bits |= (register_to_binary[rd] << 20)
                    arg_bits |= (register_to_binary[rs] << 17)
                    arg_bits |= sign_extend(k & 0xFFF, 16)

            # косвенная адресация
            elif opcode in (Opcode.SW, Opcode.LW):
                mode_bits = AddrMode.IND
                reg = args[0]
                mem = args[1]

                arg_bits |= (register_to_binary[reg] << 20)
                arg_bits |= (register_to_binary[mem["reg"]] << 17)
                arg_bits |= sign_extend(mem["offset"] & 0xFFFF, 16)

            # абсолютная адресация
            elif opcode in (Opcode.J, Opcode.JZ):
                mode_bits = AddrMode.ABS
                if opcode == Opcode.J:
                    k = args[0]
                    arg_bits |= (k & 0xFFFFF)
                elif opcode == Opcode.JZ:
                    rs, k = args[0], args[1]
                    arg_bits |= (register_to_binary[rs] << 20)
                    arg_bits |= (k & 0xFFFFF)

            else:
                raise ValueError(f"Unknown opcode: {opcode}")

            instruction = (op_bits << 26) | (mode_bits << 23) | arg_bits
            binary_bytes.extend(instruction.to_bytes(4, byteorder='big', signed=False))

    return bytes(binary_bytes)


def from_bytes(binary_code: bytes) -> dict[str, any]:
    """
    Преобразует бинарное представление машинного слова в структурированный формат
    """
    binary_instr = int.from_bytes(binary_code, byteorder='big', signed=False)

    op_bits = (binary_instr >> 26) & 0x3F
    mode_bits = (binary_instr >> 23) & 0x7
    arg_bits = binary_instr & 0x7FFFFF

    opcode = binary_to_opcode[op_bits]
    mode = AddrMode(mode_bits)

    if mode == AddrMode.REG:
        rd = binary_to_register[arg_bits >> 20]
        rs1 = binary_to_register[(arg_bits >> 17) & 0x7]
        rs2 = binary_to_register[(arg_bits >> 14) & 0x7]
        return {"opcode": opcode, "args": [rd, rs1, rs2]}
    elif mode == AddrMode.IMM:
        rd = binary_to_register[arg_bits >> 20]

        if opcode == Opcode.LUI:
            k = arg_bits & 0xFFFFF
            return {"opcode": opcode, "args": [rd, k]}

        elif opcode == Opcode.ADDI:
            rs = binary_to_register[(arg_bits >> 17) & 0x7]
            k = sign_extend(arg_bits & 0x0000FFFF, 16)
            return {"opcode": opcode, "args": [rd, rs, k]}
    elif mode == AddrMode.IND:
        reg1 = binary_to_register[arg_bits >> 20]
        reg2 = binary_to_register[(arg_bits >> 17) & 0x7]
        offset = sign_extend(arg_bits & 0xFFFF, 16)

        return {
            "opcode": opcode,
            "args": [reg1, {"offset": offset, "reg": reg2}]
        }
    elif mode == AddrMode.ABS:
        if opcode == Opcode.J:
            address = arg_bits & 0xFFFFF
            return {"opcode": opcode, "args": [address]}

        elif opcode == Opcode.JZ:
            rs = binary_to_register[arg_bits >> 20]
            address = arg_bits & 0xFFFFF
            return {"opcode": opcode, "args": [rs, address]}

    raise ValueError(f"Unknown instruction: op={op_bits}, mode={mode_bits}")


def sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    return (value ^ sign_bit) - sign_bit
