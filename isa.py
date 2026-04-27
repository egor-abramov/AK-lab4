from enum import Enum


class Opcode(str, Enum):
    LW: str = "load word"
    SW: str = "store word"
    LUI: str = "load upper immediate"
    MV: str = "move"
    ADD: str = "add"
    SUB: str = "subtract"
    MUL: str = "multiply"
    AND: str = "and"
    INV: str = "invert"
    ADDI: str = "add immediate"
    J: str = "jump"
    JZ: str = "jump zero"
    JR: str = "jump register"
    JAL: str = "jump and link"
    HALT: str = "halt"

    def __str__(self):
        return self.name


opcode_to_binary = {
    Opcode.LW: 0x0,
    Opcode.SW: 0x1,
    Opcode.LUI: 0x2,
    Opcode.JZ: 0x3,
    Opcode.JAL: 0x4,
    Opcode.MV: 0x5,
    Opcode.INV: 0x6,
    Opcode.ADDI: 0x7,
    Opcode.ADD: 0x8,
    Opcode.SUB: 0x9,
    Opcode.MUL: 0xA,
    Opcode.AND: 0xB,
    Opcode.J: 0xC,
    Opcode.JR: 0xD,
    Opcode.HALT: 0xE,
}

binary_to_opcode = {
    0x0: Opcode.LW,
    0x1: Opcode.SW,
    0x2: Opcode.LUI,
    0x3: Opcode.JZ,
    0x4: Opcode.JAL,
    0x5: Opcode.MV,
    0x6: Opcode.INV,
    0x7: Opcode.ADDI,
    0x8: Opcode.ADD,
    0x9: Opcode.SUB,
    0xA: Opcode.MUL,
    0xB: Opcode.AND,
    0xC: Opcode.J,
    0xD: Opcode.JR,
    0xE: Opcode.HALT
}
