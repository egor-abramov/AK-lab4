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
    0xD: Opcode.HALT,
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
    A0 = "a0"
    A1 = "a1"
    A2 = "a2"
    A3 = "a3"
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
    Register.A3: 0x8,
    Register.T0: 0x9,
    Register.T1: 0xA,
    Register.T2: 0xB,
    Register.T3: 0xC,
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
    0x8: Register.A3,
    0x9: Register.T0,
    0xA: Register.T1,
    0xB: Register.T2,
    0xC: Register.T3,
    0xD: Register.ZERO,
    0xE: Register.SP,
    0xF: Register.RP,
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
    ┌───────────────┬─────────┬────────────────────────────────────────────┐
    │    31...27    │  26-24  │ 23                                       0 │
    ├───────────────┼─────────┼────────────────────────────────────────────┤
    │     опкод     │ реж.адр │                аргуметны                   │
    └───────────────┴─────────┴────────────────────────────────────────────┘
    """

    binary_bytes = bytearray()
    for item in code:
        if item["type"] == "data":
            binary_bytes.extend(item["value"].to_bytes(4, byteorder="big", signed=True))
        else:
            opcode = item["opcode"]
            args = item["args"]
            op_bits = opcode_to_binary[opcode]
            arg_bits = 0

            # регистровая адресация
            if opcode in (
                Opcode.ADD,
                Opcode.SUB,
                Opcode.MUL,
                Opcode.AND,
                Opcode.MV,
                Opcode.INV,
                Opcode.JR,
                Opcode.HALT,
            ):
                mode_bits = AddrMode.REG

                if len(args) > 0:
                    arg_bits |= register_to_binary[args[0]] << 20
                if len(args) > 1:
                    arg_bits |= register_to_binary[args[1]] << 16
                if len(args) > 2:
                    arg_bits |= register_to_binary[args[2]] << 12

            # непосредственная загрузка
            elif opcode in (Opcode.LUI, Opcode.ADDI):
                mode_bits = AddrMode.IMM
                if opcode == Opcode.LUI:
                    rd, k = args[0], args[1]
                    arg_bits |= register_to_binary[rd] << 20
                    arg_bits |= k & 0xFFFFF
                elif opcode == Opcode.ADDI:
                    rd, rs, k = args[0], args[1], args[2]
                    arg_bits |= register_to_binary[rd] << 20
                    arg_bits |= register_to_binary[rs] << 16
                    arg_bits |= k & 0xFFF

            # косвенная адресация
            elif opcode in (Opcode.SW, Opcode.LW):
                mode_bits = AddrMode.IND
                reg = args[0]
                mem = args[1]

                arg_bits |= register_to_binary[reg] << 20
                arg_bits |= register_to_binary[mem["reg"]] << 16
                arg_bits |= mem["offset"] & 0xFFFF

            # абсолютная адресация
            elif opcode in (Opcode.J, Opcode.JZ):
                mode_bits = AddrMode.ABS
                if opcode == Opcode.J:
                    k = args[0]
                    arg_bits |= k & 0xFFFFF
                elif opcode == Opcode.JZ:
                    rs, k = args[0], args[1]
                    arg_bits |= register_to_binary[rs] << 20
                    arg_bits |= k & 0xFFFFF

            else:
                raise ValueError(f"Unknown opcode: {opcode}")

            instruction = (op_bits << 27) | (mode_bits << 24) | arg_bits
            binary_bytes.extend(instruction.to_bytes(4, byteorder="big", signed=False))

    return bytes(binary_bytes)


def from_bytes(binary_code: bytes) -> dict[str, any]:
    """
    Преобразует бинарное представление машинного слова в структурированный формат
    """
    binary_instr = int.from_bytes(binary_code, byteorder="big", signed=False)

    op_bits = (binary_instr >> 27) & 0x1F
    mode_bits = (binary_instr >> 24) & 0x7
    arg_bits = binary_instr & 0xFFFFFF

    opcode = binary_to_opcode[op_bits]
    mode = AddrMode(mode_bits)

    if mode == AddrMode.REG:
        rd = binary_to_register[(arg_bits >> 20) & 0xF]
        rs1 = binary_to_register[(arg_bits >> 16) & 0xF]
        rs2 = binary_to_register[(arg_bits >> 12) & 0xF]
        return {"opcode": opcode, "args": [rd, rs1, rs2]}
    elif mode == AddrMode.IMM:
        rd = binary_to_register[(arg_bits >> 20) & 0xF]

        if opcode == Opcode.LUI:
            k = arg_bits & 0xFFFFF
            return {"opcode": opcode, "args": [rd, k]}

        elif opcode == Opcode.ADDI:
            rs = binary_to_register[(arg_bits >> 16) & 0xF]
            k = arg_bits & 0xFFF
            return {"opcode": opcode, "args": [rd, rs, k]}
    elif mode == AddrMode.IND:
        reg1 = binary_to_register[(arg_bits >> 20) & 0xF]
        reg2 = binary_to_register[(arg_bits >> 16) & 0xF]
        offset = arg_bits & 0xFFFF

        return {"opcode": opcode, "args": [reg1, {"offset": offset, "reg": reg2}]}
    elif mode == AddrMode.ABS:
        if opcode == Opcode.J:
            address = arg_bits & 0xFFFFF
            return {"opcode": opcode, "args": [address]}

        elif opcode == Opcode.JZ:
            rs = binary_to_register[(arg_bits >> 20) & 0xF]
            address = arg_bits & 0xFFFFF
            return {"opcode": opcode, "args": [rs, address]}

    raise ValueError(f"Unknown instruction: op={op_bits}, mode={mode_bits}")
