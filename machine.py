import argparse
import logging
from enum import Enum, auto

from isa import Opcode, opcode_to_binary, binary_to_opcode


class Signal(int, Enum):
    WRITE_MEM = auto()
    READ_MEM = auto()
    WRITE_REG = auto()
    LATCH_PC = auto()
    LATCH_IR1 = auto()
    LATCH_IR2 = auto()
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
        if addr == self.ZERO_REGISTER_ADDR:
            return
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

    def read(self, addr: int) -> (int, int):
        if addr == self.INPUT_ADDR:
            if not self.input_buffer:
                raise EOFError("No elements in input buffer")
            return self.input_buffer.pop(0), 0
        elif (
            0 <= addr < self.MEM_SIZE - 3
            and addr != self.OUTPUT_NUM_ADDR
            and addr != self.OUTPUT_CHAR_ADDR
        ):
            second_word = 0
            if addr + 4 < self.MEM_SIZE - 3:
                second_word = (
                    (self.mem[addr + 4] << 24)
                    | (self.mem[addr + 5] << 16)
                    | (self.mem[addr + 6] << 8)
                    | self.mem[addr + 7]
                )

            first_word = (
                (self.mem[addr] << 24)
                | (self.mem[addr + 1] << 16)
                | (self.mem[addr + 2] << 8)
                | self.mem[addr + 3]
            )
            return first_word, second_word
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
        self.IR1 = 0x0
        self.IR2 = 0x0
        self.AR1 = 0x0
        self.AR2 = 0x0
        self.flags = {"N": 0, "Z": 0}

    def tick(self, signals1: [Signal], signals2: [Signal]):
        # Decode IR1
        rd1_idx = (self.IR1 >> 23) & 0xF
        rs1_1_idx = (self.IR1 >> 19) & 0xF
        rs2_1_idx = (self.IR1 >> 15) & 0xF
        imm_1_ir = self.IR1 & 0xFFFFF

        # Decode IR2
        rd2_idx = (self.IR2 >> 23) & 0xF
        rs1_2_idx = (self.IR2 >> 19) & 0xF
        rs2_2_idx = (self.IR2 >> 15) & 0xF
        imm_2_ir = self.IR2 & 0xFFFFF

        rs1_1_data = self.reg_file.read_rs(rs1_1_idx)
        rs2_1_data = self.reg_file.read_rs(rs2_1_idx)
        rs1_2_data = self.reg_file.read_rs(rs1_2_idx)
        rs2_2_data = self.reg_file.read_rs(rs2_2_idx)

        imm_1_data = self._imm_generator(imm_1_ir, signals1)
        imm_2_data = self._imm_generator(imm_2_ir, signals2)

        # ALU 1
        alu1_l, alu1_r = 0, 0
        if Signal.SEL_ALU_L_PC in signals1:
            alu1_l = self.PC
        if Signal.SEL_ALU_L_RS1 in signals1:
            alu1_l = rs1_1_data

        if Signal.SEL_ALU_R_IMM in signals1:
            alu1_r = imm_1_data
        if Signal.SEL_ALU_R_RS2 in signals1:
            alu1_r = rs2_1_data
        alu1_res, flags1 = self._alu_execute(alu1_l, alu1_r, signals1)

        # ALU 2
        alu2_l, alu2_r = 0, 0
        if Signal.SEL_ALU_L_PC in signals2:
            alu2_l = self.PC
        if Signal.SEL_ALU_L_RS1 in signals2:
            alu2_l = rs1_2_data

        if Signal.SEL_ALU_R_IMM in signals2:
            alu2_r = imm_2_data
        if Signal.SEL_ALU_R_RS2 in signals2:
            alu2_r = rs2_2_data
        alu2_res, flags2 = self._alu_execute(alu2_l, alu2_r, signals2)

        # New flags
        alu_op_signals = {
            Signal.ALU_OP_PLUS,
            Signal.ALU_OP_MINUS,
            Signal.ALU_OP_MUL,
            Signal.ALU_OP_DIV,
            Signal.ALU_OP_MOD,
            Signal.ALU_OP_AND,
            Signal.ALU_OP_INV,
            Signal.ALU_OP_PASS_L,
            Signal.ALU_OP_PASS_R,
        }
        sig2_updates_flags = any(sig in alu_op_signals for sig in signals2)

        if sig2_updates_flags:
            self.flags = flags2
        else:
            self.flags = flags1

        # Select memory address source
        mem_addr = 0
        if Signal.SEL_MEM_ADDR_AR in signals1:
            mem_addr = self.AR1
        elif Signal.SEL_MEM_ADDR_AR in signals2:
            mem_addr = self.AR2
        elif Signal.SEL_MEM_ADDR_PC in signals1 or Signal.SEL_MEM_ADDR_PC in signals2:
            mem_addr = self.PC

        # Write mem
        if Signal.WRITE_MEM in signals1:
            self.memory.write(rs2_1_data, mem_addr)
        elif Signal.WRITE_MEM in signals2:
            self.memory.write(rs2_2_data, mem_addr)

        # Read memory
        mem_data_out_1 = 0
        mem_data_out_2 = 0
        if Signal.READ_MEM in signals1 or Signal.READ_MEM in signals2:
            mem_data_out_1, mem_data_out_2 = self.memory.read(mem_addr)

        # Data to register
        reg_write_data_1 = 0
        if Signal.SEL_REG_SR_MEM in signals1:
            reg_write_data_1 = mem_data_out_1
        elif Signal.SEL_REG_SR_ALU in signals1:
            reg_write_data_1 = alu1_res

        reg_write_data_2 = 0
        if Signal.SEL_REG_SR_MEM in signals2:
            reg_write_data_2 = mem_data_out_1
        elif Signal.SEL_REG_SR_ALU in signals2:
            reg_write_data_2 = alu2_res

        # Write to register
        if Signal.WRITE_REG in signals1:
            self.reg_file.write_rd(reg_write_data_1, rd1_idx)
        if Signal.WRITE_REG in signals2:
            self.reg_file.write_rd(reg_write_data_2, rd2_idx)

        # Latch Address Register
        if Signal.LATCH_AR in signals1:
            self.AR1 = alu1_res & 0xFFFFFFFF
        if Signal.LATCH_AR in signals2:
            self.AR2 = alu2_res & 0xFFFFFFFF

        # Latch Instruction Register
        if Signal.LATCH_IR1 in signals1 or Signal.LATCH_IR1 in signals2:
            self.IR1 = mem_data_out_1 & 0xFFFFFFFF
        if Signal.LATCH_IR2 in signals1 or Signal.LATCH_IR2 in signals2:
            self.IR2 = mem_data_out_2 & 0xFFFFFFFF

        # Inc Program Counter
        pc_inc = 0
        if Signal.SEL_NEXT_PC_INC in signals1:
            pc_inc += 4
        if Signal.SEL_NEXT_PC_INC in signals2:
            pc_inc += 4

        if Signal.SEL_NEXT_PC_ALU in signals1:
            new_pc = alu1_res
        elif Signal.SEL_NEXT_PC_ALU in signals2:
            new_pc = alu2_res
        else:
            new_pc = self.PC + pc_inc

        # Latch Program Counter
        if Signal.LATCH_PC in signals1 or Signal.LATCH_PC in signals2:
            self.PC = new_pc & 0xFFFFFFFF

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
            x &= 0xFFFF
            n = 16
        elif Signal.SEL_IMM_MODE_U in signals:
            return (x & 0xFFFFF) << 12
        else:
            return x
        sign_bit = 1 << (n - 1)
        return (x & (sign_bit - 1)) - (x & sign_bit)


class ControlUnit:
    def __init__(self, data_path: DataPath, scalar_mode: bool = False):
        self.data_path = data_path
        self.mPC1 = 0x0
        self.mPC2 = 0x0
        self.scalar_mode = scalar_mode

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

        self.SEQ_INC = 0
        self.SEQ_MAP = 1
        self.SEQ_JMP = 2
        self.SEQ_JMP_Z = 3
        self.SEQ_JMP_L = 4
        self.SEQ_JMP_G = 5

        self.mp_memory = {
            # FETCH
            0x0: MicroCommand(
                [
                    Signal.SEL_MEM_ADDR_PC,
                    Signal.READ_MEM,
                    Signal.LATCH_IR1,
                    Signal.LATCH_IR2,
                ],
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
            # Force WAIT
            0x19: MicroCommand([]),
        }

    def _issue_logic(self, ir1: int, ir2: int) -> bool:
        if self.scalar_mode:
            return False

        opcode_1 = binary_to_opcode.get((ir1 >> 27) & 0x1F)
        opcode_2 = binary_to_opcode.get((ir2 >> 27) & 0x1F)

        branches = {Opcode.J, Opcode.JR, Opcode.JZ, Opcode.JG, Opcode.JL, Opcode.HALT}
        mem_ops = {Opcode.LW, Opcode.SW}

        if opcode_2 is None:
            return False

        if opcode_1 in branches:
            return False

        if opcode_1 == Opcode.HALT or opcode_2 == Opcode.HALT:
            return False

        if opcode_1 in mem_ops and opcode_2 in mem_ops:
            return False

        rd1 = (ir1 >> 23) & 0xF
        rs2_1 = (ir1 >> 15) & 0xF

        rd2 = (ir2 >> 23) & 0xF
        rs1_2 = (ir2 >> 19) & 0xF
        rs2_2 = (ir2 >> 15) & 0xF

        def get_reads(opcode, r1, r2):
            r = []
            if opcode in {
                Opcode.MV,
                Opcode.SW,
                Opcode.LW,
                Opcode.ADDI,
                Opcode.ADD,
                Opcode.SUB,
                Opcode.MUL,
                Opcode.AND,
                Opcode.INV,
                Opcode.DIV,
                Opcode.MOD,
                Opcode.JR,
                Opcode.JZ,
                Opcode.JG,
                Opcode.JL,
            }:
                r.append(r1)
            if opcode in {
                Opcode.SW,
                Opcode.ADD,
                Opcode.SUB,
                Opcode.MUL,
                Opcode.AND,
                Opcode.DIV,
                Opcode.MOD,
            }:
                r.append(r2)
            return r

        def get_write(op_enum, rd):
            if op_enum in {
                Opcode.LUI,
                Opcode.MV,
                Opcode.LW,
                Opcode.ADDI,
                Opcode.ADD,
                Opcode.SUB,
                Opcode.MUL,
                Opcode.AND,
                Opcode.INV,
                Opcode.DIV,
                Opcode.MOD,
            }:
                return rd
            return None

        w1 = get_write(opcode_1, rd1)

        w2 = get_write(opcode_2, rd2)
        r2 = get_reads(opcode_2, rs1_2, rs2_2)

        if w1 is not None and w1 != self.data_path.reg_file.ZERO_REGISTER_ADDR:
            if w1 in r2 or w1 == w2:
                return False

        if w2 is not None and w2 != self.data_path.reg_file.ZERO_REGISTER_ADDR:
            if opcode_1 == Opcode.SW and w2 == rs2_1:
                return False

        return True

    def _next_mpc(self, mPC: int, mc: MicroCommand) -> int:
        jmp_mode = mc.jmp_mode
        jmp_addr = mc.jmp_addr
        opcode = (self.data_path.IR1 >> 27) & 0x1F
        if jmp_mode == self.SEQ_INC:
            return mPC + 1
        elif jmp_mode == self.SEQ_MAP:
            return self.dispatch_table.get(opcode, 0)
        elif jmp_mode == self.SEQ_JMP:
            return jmp_addr
        elif jmp_mode == self.SEQ_JMP_Z:
            if self.data_path.flags.get("Z", False):
                return jmp_addr
            return mPC + 1
        elif jmp_mode == self.SEQ_JMP_G:
            n = self.data_path.flags.get("N", False)
            z = self.data_path.flags.get("Z", False)
            if not n and not z:
                return jmp_addr
            return mPC + 1
        elif jmp_mode == self.SEQ_JMP_L:
            n = self.data_path.flags.get("N", False)
            z = self.data_path.flags.get("Z", False)
            if n and not z:
                return jmp_addr
            return mPC + 1
        return 0

    def tick(self):
        if self.mPC1 == self.dispatch_table[opcode_to_binary[Opcode.HALT]]:
            raise StopIteration()

        # Sync Logic
        if self.mPC1 == 0 and self.mPC2 != 0:
            mc1 = self.mp_memory[0x19]
            mc2 = self.mp_memory.get(self.mPC2, self.mp_memory[0x19])
        elif self.mPC2 == 0 and self.mPC1 != 0:
            mc1 = self.mp_memory.get(self.mPC1, self.mp_memory[0x19])
            mc2 = self.mp_memory[0x19]
        else:
            mc1 = self.mp_memory.get(self.mPC1, self.mp_memory[0x19])
            mc2 = self.mp_memory.get(self.mPC2, self.mp_memory[0x19])

        self.data_path.tick(mc1.signals, mc2.signals)

        if mc1.jmp_mode == self.SEQ_MAP and self.mPC1 == 0 and self.mPC2 == 0:
            op1 = (self.data_path.IR1 >> 27) & 0x1F
            op2 = (self.data_path.IR2 >> 27) & 0x1F

            self.mPC1 = self.dispatch_table.get(op1, 0x18)

            if self._issue_logic(self.data_path.IR1, self.data_path.IR2):
                self.mPC2 = self.dispatch_table.get(op2, 0x18)
            else:
                self.mPC2 = 0x0
        else:
            self.mPC1 = self._next_mpc(self.mPC1, mc1)
            self.mPC2 = self._next_mpc(self.mPC2, mc2)


def simulation(
    initial_mem: [int],
    input_token: [str],
    scalar_mode: bool = True,
):
    memory = Memory(initial_mem, input_token)
    data_path = DataPath(memory)
    control_unit = ControlUnit(data_path, scalar_mode)
    ticks = 0
    trace_log = []

    if scalar_mode:
        logging.info("Superscalar mode disabled")

    try:
        while True:
            control_unit.tick()
            ticks += 1

            if ticks <= 1000:
                pc_str = f"PC: 0x{data_path.PC:02X}"
                mpc_str = f"m1:{control_unit.mPC1:02X} m2:{control_unit.mPC2:02X}"

                opcode_1 = binary_to_opcode.get((data_path.IR1 >> 27) & 0x1F)
                opcode_2 = binary_to_opcode.get((data_path.IR2 >> 27) & 0x1F)

                opcode_1_str = (
                    opcode_1.name
                    if opcode_1 and control_unit.mPC1 not in [0, 0x19]
                    else "IDLE"
                )
                opcode_2_str = (
                    opcode_2.name
                    if opcode_2 and control_unit.mPC2 not in [0, 0x19]
                    else "IDLE"
                )

                if control_unit.mPC1 == 0 and control_unit.mPC2 == 0:
                    opcode_1_str = "FETCH"
                    opcode_2_str = "FETCH"

                flags_str = f"Z:{data_path.flags['Z']} N:{data_path.flags['N']}"

                trace_line = f"Tick: {ticks:04d} | {pc_str:9} | {mpc_str:9} | {opcode_1_str:>5} | {opcode_2_str:>5} |{flags_str}"
                trace_log.append(trace_line)
    except StopIteration:
        pass
    logging.info(f"Ticks executed: {ticks}")
    logging.info("Output:")
    logging.info("".join(memory.output_buffer) + "\n")
    logging.info("Trace:")
    for trace_line in trace_log:
        logging.info(trace_line)


def main(source_path: str, input_path: str, scalar_mode: bool = False):
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
    simulation(initial_mem, input_tokens, scalar_mode)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("source_file", nargs="?", default="./examples/prob1/prob1.bin")
    parser.add_argument("input_file", nargs="?", default="./examples/prob1/prob1.txt")
    parser.add_argument("--scalar-mode", action="store_true")

    args = parser.parse_args()
    main(args.source_file, args.input_file, args.scalar_mode)
