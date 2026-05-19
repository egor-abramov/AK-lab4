import argparse
import logging
from enum import Enum, auto

from isa import Opcode, opcode_to_binary, binary_to_opcode


class Signal(int, Enum):
    WRITE_MEM = auto()
    READ_MEM = auto()
    WRITE_REG = auto()
    LATCH_PC = auto()
    LATCH_IR = auto()
    LATCH_AR = auto()
    SEL_ALU_L_PC = auto()
    SEL_ALU_L_RS1 = auto()
    SEL_ALU_R_RS2 = auto()
    SEL_ALU_R_IMM = auto()
    ALU_OP_PASS_R = auto()
    ALU_OP_PASS_L = auto()
    ALU_OP_PLUS = auto()
    ALU_OP_MINUS = auto()
    ALU_OP_MUL = auto()
    ALU_OP_DIV = auto()
    ALU_OP_MOD = auto()
    ALU_OP_AND = auto()
    ALU_OP_INV = auto()
    SEL_IMM_MODE_16 = auto()
    SEL_IMM_MODE_20 = auto()
    SEL_IMM_MODE_12 = auto()
    SEL_IMM_MODE_U = auto()
    SEL_MEM_ADDR_PC = auto()
    SEL_MEM_ADDR_AR = auto()
    SEL_REG_SR_MEM = auto()
    SEL_REG_SR_ALU = auto()
    SEL_NEXT_PC_INC = auto()
    SEL_NEXT_PC_ALU = auto()


class MicroCommand:
    def __init__(self, signals: [Signal], jmp_mode: int = 2, jmp_addr: int = 0x0):
        self.signals = signals
        self.jmp_mode = jmp_mode
        self.jmp_addr = jmp_addr


class RegisterFile:
    def __init__(
        self,
        register_count: int = 16,
        register_len: int = 32,
        zero_register_addr: int = 0xD,
    ):
        self.REGISTER_COUNT = register_count
        self.ZERO_REGISTER_ADDR = zero_register_addr
        self.REGISTER_LEN = register_len
        self.regs = [0] * self.REGISTER_COUNT

    def read_rs(self, addr: int) -> int:
        if addr == self.ZERO_REGISTER_ADDR:
            return 0
        return self.regs[addr]

    def write_rd(self, val: int, addr: int):
        self.regs[addr] = val & ((1 << self.REGISTER_LEN) - 1)


class Memory:
    def __init__(
        self,
        initial_mem: [int],
        input_buffer: [str],
        mem_size: int = 0x4000,
        input_addr: int = 0x3EF8,
        output_num_addr: int = 0x3EFC,
        output_char_addr: int = 0x3F00,
    ):
        self.INPUT_ADDR = input_addr
        self.OUTPUT_NUM_ADDR = output_num_addr
        self.OUTPUT_CHAR_ADDR = output_char_addr

        self.MEM_SIZE = mem_size
        self.mem = [0] * self.MEM_SIZE
        for i in range(len(initial_mem)):
            self.mem[i] = initial_mem[i]
        self.input_buffer = input_buffer
        self.output_buffer = []

    def read(self, addr: int) -> int:
        if addr == self.INPUT_ADDR:
            if not self.input_buffer:
                raise EOFError("No elements in input buffer")
            return self.input_buffer.pop(0)
        elif (
            0 <= addr < self.MEM_SIZE - 3
            and addr != self.OUTPUT_NUM_ADDR
            and addr != self.OUTPUT_CHAR_ADDR
        ):
            return (
                (self.mem[addr] << 24)
                | (self.mem[addr + 1] << 16)
                | (self.mem[addr + 2] << 8)
                | self.mem[addr + 3]
            )
        raise Exception(f"Invalid memory access at address {addr}")

    def write(self, val: int, addr: int):
        if addr == self.OUTPUT_NUM_ADDR:
            if val & (1 << 31):
                val -= 1 << 32
            self.output_buffer.append(f"{val} ")
        elif addr == self.OUTPUT_CHAR_ADDR:
            self.output_buffer.append(chr(val))
        elif 0 <= addr < self.MEM_SIZE - 3 and addr != self.INPUT_ADDR:
            self.mem[addr] = (val >> 24) & 0xFF
            self.mem[addr + 1] = (val >> 16) & 0xFF
            self.mem[addr + 2] = (val >> 8) & 0xFF
            self.mem[addr + 3] = val & 0xFF
        else:
            raise Exception(f"Invalid memory access at address {addr}")


class DataPath:
    def __init__(self, memory: Memory):
        self.memory = memory
        self.reg_file = RegisterFile()
        self.PC = 0x0
        self.IR = 0x0
        self.AR = 0x0
        self.flags = {"N": 0, "Z": 0}

    def tick(self, signals: [Signal]):
        rd_idx = (self.IR >> 23) & 0xF
        rs1_idx = (self.IR >> 19) & 0xF
        rs2_idx = (self.IR >> 15) & 0xF
        imm_ir = self.IR & 0xFFFFF

        rs1_data = self.reg_file.read_rs(rs1_idx)
        rs2_data = self.reg_file.read_rs(rs2_idx)

        imm_data = self._imm_generator(imm_ir, signals)

        alu_l, alu_r = 0, 0
        if Signal.SEL_ALU_L_PC in signals:
            alu_l = self.PC
        if Signal.SEL_ALU_L_RS1 in signals:
            alu_l = rs1_data

        if Signal.SEL_ALU_R_IMM in signals:
            alu_r = imm_data
        if Signal.SEL_ALU_R_RS2 in signals:
            alu_r = rs2_data

        alu_res, self.flags = self._alu_execute(alu_l, alu_r, signals)

        new_pc = 0
        if Signal.SEL_NEXT_PC_INC in signals:
            new_pc = self.PC + 4
        if Signal.SEL_NEXT_PC_ALU in signals:
            new_pc = alu_res

        mem_addr = 0
        if Signal.SEL_MEM_ADDR_AR in signals:
            mem_addr = self.AR
        if Signal.SEL_MEM_ADDR_PC in signals:
            mem_addr = self.PC

        if Signal.WRITE_MEM in signals:
            self.memory.write(rs2_data, mem_addr)

        mem_data_out = 0
        if Signal.READ_MEM in signals:
            mem_data_out = self.memory.read(mem_addr)

        reg_write_data = 0
        if Signal.SEL_REG_SR_MEM in signals:
            reg_write_data = mem_data_out
        if Signal.SEL_REG_SR_ALU in signals:
            reg_write_data = alu_res

        if Signal.WRITE_REG in signals:
            self.reg_file.write_rd(reg_write_data, rd_idx)

        if Signal.LATCH_PC in signals:
            self.PC = new_pc & 0xFFFFFFFF

        if Signal.LATCH_IR in signals:
            self.IR = mem_data_out & 0xFFFFFFFF

        if Signal.LATCH_AR in signals:
            self.AR = alu_res & 0xFFFFFFFF

    def _alu_execute(self, x: int, y: int, signals: [Signal]) -> (int, dict[str, int]):
        res = 0
        if Signal.ALU_OP_PLUS in signals:
            res = x + y
        elif Signal.ALU_OP_MINUS in signals:
            res = x - y
        elif Signal.ALU_OP_MUL in signals:
            res = x * y
        elif Signal.ALU_OP_AND in signals:
            res = x & y
        elif Signal.ALU_OP_INV in signals:
            res = ~x
        elif Signal.ALU_OP_PASS_L in signals:
            res = x
        elif Signal.ALU_OP_PASS_R in signals:
            res = y
        elif Signal.ALU_OP_DIV in signals:
            res = 0 if y == 0 else x // y
        elif Signal.ALU_OP_MOD in signals:
            res = 0 if y == 0 else x % y
        res &= 0xFFFFFFFF
        flags = {"N": (res >> 31) & 1, "Z": 1 if res == 0 else 0}
        return res, flags

    def _imm_generator(self, x: int, signals: [Signal]):
        if Signal.SEL_IMM_MODE_12 in signals:
            x &= 0xFFF
            n = 12
        elif Signal.SEL_IMM_MODE_20 in signals:
            x &= 0xFFFFF
            n = 20
        elif Signal.SEL_IMM_MODE_16 in signals:
            x &= 0x7FFF
            n = 15
        elif Signal.SEL_IMM_MODE_U in signals:
            return (x & 0xFFFFF) << 12
        else:
            return x
        sign_bit = 1 << (n - 1)
        return (x & (sign_bit - 1)) - (x & sign_bit)


class ControlUnit:
    def __init__(self, data_path: DataPath):
        self.data_path = data_path
        self.mPC = 0x0

        # Опкод в адрес начала микропограммы
        self.dispatch_table = {
            opcode_to_binary[Opcode.LUI]: 0x1,
            opcode_to_binary[Opcode.MV]: 0x2,
            opcode_to_binary[Opcode.SW]: 0x3,
            opcode_to_binary[Opcode.LW]: 0x5,
            opcode_to_binary[Opcode.ADDI]: 0x7,
            opcode_to_binary[Opcode.ADD]: 0x8,
            opcode_to_binary[Opcode.SUB]: 0x9,
            opcode_to_binary[Opcode.MUL]: 0xA,
            opcode_to_binary[Opcode.AND]: 0xB,
            opcode_to_binary[Opcode.INV]: 0xC,
            opcode_to_binary[Opcode.DIV]: 0xD,
            opcode_to_binary[Opcode.MOD]: 0xE,
            opcode_to_binary[Opcode.J]: 0xF,
            opcode_to_binary[Opcode.JR]: 0x10,
            opcode_to_binary[Opcode.JZ]: 0x11,
            opcode_to_binary[Opcode.JG]: 0x14,
            opcode_to_binary[Opcode.JL]: 0x16,
            opcode_to_binary[Opcode.HALT]: 0x18,
        }

        # Стратегии выбора следующего mPC
        self.SEQ_INC = 0  # pc + 4
        self.SEQ_MAP = 1  # переход по dispatch_table
        self.SEQ_JMP = 2  # безусловный
        self.SEQ_JMP_Z = 3  # условный (z == 1)
        self.SEQ_JMP_L = 3  # условный (n == 1 ^ z == 0)
        self.SEQ_JMP_G = 4

        self.mp_memory = {
            # FETCH
            0x0: MicroCommand(
                [Signal.SEL_MEM_ADDR_PC, Signal.READ_MEM, Signal.LATCH_IR],
                jmp_mode=self.SEQ_MAP,
            ),
            # LUI
            0x1: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_IMM_MODE_U,
                    Signal.SEL_ALU_R_IMM,
                    Signal.ALU_OP_PASS_R,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # MV
            0x2: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.ALU_OP_PASS_L,
                    Signal.SEL_REG_SR_ALU,
                    Signal.WRITE_REG,
                ]
            ),
            # SW
            0x3: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_IMM,
                    Signal.ALU_OP_PLUS,
                    Signal.LATCH_AR,
                    Signal.SEL_IMM_MODE_12,
                ],
                jmp_mode=self.SEQ_INC,
            ),
            0x4: MicroCommand(
                [
                    Signal.SEL_MEM_ADDR_AR,
                    Signal.WRITE_MEM,
                ]
            ),
            # LW
            0x5: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_IMM,
                    Signal.ALU_OP_PLUS,
                    Signal.LATCH_AR,
                    Signal.SEL_IMM_MODE_12,
                ],
                jmp_mode=self.SEQ_INC,
            ),
            0x6: MicroCommand(
                [
                    Signal.SEL_MEM_ADDR_AR,
                    Signal.READ_MEM,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_MEM,
                ]
            ),
            # ADDI
            0x7: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_IMM,
                    Signal.SEL_IMM_MODE_12,
                    Signal.ALU_OP_PLUS,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ],
            ),
            # ADD
            0x8: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_RS2,
                    Signal.ALU_OP_PLUS,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # SUB
            0x9: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_RS2,
                    Signal.ALU_OP_MINUS,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # MUL
            0xA: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_RS2,
                    Signal.ALU_OP_MUL,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # AND
            0xB: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_RS2,
                    Signal.ALU_OP_AND,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # INV
            0xC: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_RS2,
                    Signal.ALU_OP_INV,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # DIV
            0xD: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_RS2,
                    Signal.ALU_OP_DIV,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # MOD
            0xE: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                    Signal.SEL_ALU_L_RS1,
                    Signal.SEL_ALU_R_RS2,
                    Signal.ALU_OP_MOD,
                    Signal.WRITE_REG,
                    Signal.SEL_REG_SR_ALU,
                ]
            ),
            # J
            0xF: MicroCommand(
                [
                    Signal.SEL_ALU_R_IMM,
                    Signal.ALU_OP_PASS_R,
                    Signal.SEL_NEXT_PC_ALU,
                    Signal.LATCH_PC,
                ]
            ),
            # JR
            0x10: MicroCommand(
                [
                    Signal.SEL_ALU_L_RS1,
                    Signal.ALU_OP_PASS_L,
                    Signal.SEL_NEXT_PC_ALU,
                    Signal.LATCH_PC,
                ]
            ),
            # JZ
            0x11: MicroCommand(
                [
                    Signal.SEL_ALU_L_RS1,
                    Signal.ALU_OP_PASS_L,
                ],
                jmp_mode=self.SEQ_JMP_Z,
                jmp_addr=0x13,
            ),
            0x12: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                ]
            ),
            0x13: MicroCommand(
                [
                    Signal.SEL_ALU_R_IMM,
                    Signal.ALU_OP_PASS_R,
                    Signal.SEL_NEXT_PC_ALU,
                    Signal.LATCH_PC,
                ]
            ),
            # JG
            0x14: MicroCommand(
                [
                    Signal.SEL_ALU_L_RS1,
                    Signal.ALU_OP_PASS_L,
                ],
                jmp_mode=self.SEQ_JMP_G,
                jmp_addr=0x13,
            ),
            0x15: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                ]
            ),
            # JL
            0x16: MicroCommand(
                [
                    Signal.SEL_ALU_L_RS1,
                    Signal.ALU_OP_PASS_L,
                ],
                jmp_mode=self.SEQ_JMP_L,
                jmp_addr=0x13,
            ),
            0x17: MicroCommand(
                [
                    Signal.SEL_NEXT_PC_INC,
                    Signal.LATCH_PC,
                ]
            ),
            # HALT
            0x18: MicroCommand([], jmp_addr=0x18),
        }

    def tick(self):
        if self.mPC == self.dispatch_table[opcode_to_binary[Opcode.HALT]]:
            raise StopIteration()

        mc: MicroCommand = self.mp_memory.get(self.mPC, 0)

        self.data_path.tick(mc.signals)

        jmp_mode = mc.jmp_mode
        jmp_addr = mc.jmp_addr
        opcode = (self.data_path.IR >> 27) & 0x1F
        if jmp_mode == self.SEQ_INC:
            self.mPC += 1
        elif jmp_mode == self.SEQ_MAP:
            self.mPC = self.dispatch_table.get(opcode, 0)
        elif jmp_mode == self.SEQ_JMP:
            self.mPC = jmp_addr
        elif jmp_mode == self.SEQ_JMP_Z:
            if self.data_path.flags.get("Z", False):
                self.mPC = jmp_addr
            else:
                self.mPC += 1
        elif jmp_mode == self.SEQ_JMP_G:
            n = self.data_path.flags.get("N", False)
            z = self.data_path.flags.get("Z", False)
            if not n and not z:
                self.mPC = jmp_addr
            else:
                self.mPC += 1
        elif jmp_mode == self.SEQ_JMP_L:
            n = self.data_path.flags.get("N", False)
            z = self.data_path.flags.get("Z", False)
            if n and not z:
                self.mPC = jmp_addr
            else:
                self.mPC += 1


def simulation(initial_mem: [int], input_token: [str], trace_regs: list[int] = None):
    memory = Memory(initial_mem, input_token)
    data_path = DataPath(memory)
    control_unit = ControlUnit(data_path)
    ticks = 0
    trace_log = []
    try:
        while True:
            control_unit.tick()
            ticks += 1

            if ticks <= 1000:
                pc_str = f"PC: 0x{data_path.PC:02X}"
                mpc_str = f"mPC: 0x{control_unit.mPC:02X}"
                opcode = binary_to_opcode[(data_path.IR >> 27) & 0x1F]
                flags_str = f"Z: {data_path.flags['Z']} N: {data_path.flags['N']}"

                if trace_regs is not None:
                    regs_str = " | ".join(
                        [
                            f"R{r}: 0x{data_path.reg_file.read_rs(r):08X}"
                            for r in trace_regs
                        ]
                    )
                    trace_line = f"Tick: {ticks:04d} | {pc_str:9} | {mpc_str:9} | {opcode:>4} | {flags_str} | {regs_str}"
                else:
                    trace_line = f"Tick: {ticks:04d} | {pc_str:9} | {mpc_str:9} | {opcode:>4} | {flags_str}"
                trace_log.append(trace_line)
    except StopIteration:
        pass
    logging.info(f"Ticks executed: {ticks}")
    logging.info("Output:")
    logging.info("".join(memory.output_buffer) + "\n")
    logging.info("Trace:")
    for trace_line in trace_log:
        logging.info(trace_line)


def main(source_path: str, input_path: str, trace_regs: list[int] = None):
    with open(source_path, "rb") as f:
        initial_mem = list(f.read())

    with open(input_path, encoding="utf-8") as f:
        data = f.read()
        input_tokens = []
        for ch in data:
            if isinstance(ch, int):
                input_tokens.append(int(ch))
            else:
                input_tokens.append(ord(ch))
        input_tokens.append(ord("\n"))
    simulation(initial_mem, input_tokens, trace_regs)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("source_file", nargs="?", default="./examples/prob1/prob1.bin")
    parser.add_argument("input_file", nargs="?", default="./examples/prob1/prob1.txt")
    parser.add_argument("--trace", nargs="+", type=int)

    args = parser.parse_args()
    main(args.source_file, args.input_file, args.trace)
