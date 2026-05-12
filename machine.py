import argparse
import logging

from isa import Opcode, opcode_to_binary, binary_to_opcode


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
        mem_size: int = 4096,
        input_addr: int = 3800,
        output_num_addr: int = 3804,
        output_char_addr: int = 3808,
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
        self.flags = {"N": 0, "Z": 0}

    def tick(self, signals: dict[str, any]):
        rd_idx = (self.IR >> 23) & 0xF
        rs1_idx = (self.IR >> 19) & 0xF
        rs2_idx = (self.IR >> 15) & 0xF
        imm_ir = self.IR & 0xFFFFF

        rs1_data = self.reg_file.read_rs(rs1_idx)
        rs2_data = self.reg_file.read_rs(rs2_idx)

        sel_ext_mode = signals.get("sel_ext_mode", "None")
        imm_data = self._sign_extend(imm_ir, sel_ext_mode)

        sel_alu_l = signals.get("sel_alu_l", "RS1")
        if sel_alu_l == "PC":
            alu_l = self.PC
        else:
            alu_l = rs1_data

        sel_alu_r = signals.get("sel_alu_r", "RS2")
        if sel_alu_r == "INC_PC":
            alu_r = 4
        elif sel_alu_r == "IMM":
            alu_r = imm_data
        else:
            alu_r = rs2_data

        alu_op = signals.get("alu_op", "PASS_L")
        alu_res, self.flags = self._alu_execute(alu_op, alu_l, alu_r)

        sel_mem_addr = signals.get("sel_mem_addr", "PC")
        if sel_mem_addr == "ALU":
            mem_addr = alu_res
        else:
            mem_addr = self.PC

        if signals.get("write_mem", False):
            self.memory.write(rs2_data, mem_addr)

        mem_data_out = 0
        if signals.get("read_mem", False):
            mem_data_out = self.memory.read(mem_addr)

        sel_reg_wr = signals.get("sel_reg_wr", "ALU")
        if sel_reg_wr == "MEM":
            reg_write_data = mem_data_out
        else:
            reg_write_data = alu_res

        if signals.get("write_reg", False):
            self.reg_file.write_rd(reg_write_data, rd_idx)

        if signals.get("latch_pc", False):
            self.PC = alu_res & 0xFFFFFFFF

        if signals.get("latch_ir", False):
            self.IR = mem_data_out & 0xFFFFFFFF

    def _alu_execute(self, op, x, y) -> (int, dict[str, int]):
        res = 0
        if op == "ADD":
            res = x + y
        elif op == "SUB":
            res = x - y
        elif op == "MUL":
            res = x * y
        elif op == "AND":
            res = x & y
        elif op == "INV":
            res = ~x
        elif op == "PASS_L":
            res = x
        elif op == "PASS_R":
            res = y
        res &= 0xFFFFFFFF
        flags = {"N": 1 if (res >> 31) & 1 else 0, "Z": 1 if res == 0 else 0}
        return res, flags

    def _sign_extend(self, x: int, mode: str):
        if mode == "IMM_12":
            x &= 0xFFF
            n = 12
        elif mode == "IMM_20":
            x &= 0xFFFFF
            n = 20
        elif mode == "OFFSET_16":
            x &= 0x7FFF
            n = 16
        elif mode == "IMM_U":
            return (x & 0xFFFFF) << 12
        else:
            return 0
        sign_bit = 1 << (n - 1)
        return (x & (sign_bit - 1)) - (x & sign_bit)


class ControlUnit:
    """
    Блок управления процессора. Управление осуществляется при помощи микрокоманд.
    Инструкция декодируется в надор микрокоманд.

    Для удобства микрокоманды можно записывать в словари, где ключ - это управляющий сигнал, а данные - это значение сигнала.
    Такой далее словарь транслируется в микрокоманду (24 бита) и передается в DataPath
    """

    def __init__(self, data_path: DataPath):
        self.data_path = data_path
        self.mPC = 0x0

        # Опкод в адрес начала микропограммы
        self.dispatch_table = {
            opcode_to_binary[Opcode.LUI]: 0x2,
            opcode_to_binary[Opcode.MV]: 0x3,
            opcode_to_binary[Opcode.SW]: 0x4,
            opcode_to_binary[Opcode.LW]: 0x5,
            opcode_to_binary[Opcode.ADDI]: 0x6,
            opcode_to_binary[Opcode.ADD]: 0x7,
            opcode_to_binary[Opcode.SUB]: 0x8,
            opcode_to_binary[Opcode.MUL]: 0x9,
            opcode_to_binary[Opcode.AND]: 0xA,
            opcode_to_binary[Opcode.INV]: 0xB,
            opcode_to_binary[Opcode.J]: 0xC,
            opcode_to_binary[Opcode.JR]: 0xD,
            opcode_to_binary[Opcode.JZ]: 0xE,
            opcode_to_binary[Opcode.HALT]: 0x11,
        }

        # Типы переходов после исполнения микрокоманды
        self.SEQ_INC = 0  # pc + 4
        self.SEQ_MAP = 1  # переход по dispatch_table
        self.SEQ_JMP = 2  # безусловный
        self.SEQ_JMP_Z = 3  # условный (z == 0)

        # Режимы расширения знака
        EXT_MODE_12 = 0
        EXT_MODE_20 = 1
        EXT_MODE_16 = 2
        EXT_MODE_U = 3

        self.SHIFT_LATCH_PC = 0
        self.SHIFT_LATCH_IR = 1
        self.SHIFT_READ_MEM = 2
        self.SHIFT_WRITE_MEM = 3
        self.SHIFT_WRITE_REG = 4
        self.SHIFT_SEL_MEM_ADDR = 5
        self.SHIFT_SEL_REG_WR = 6
        self.SHIFT_SEL_ALU_L = 7
        self.SHIFT_SEL_ALU_R = 8
        self.SHIFT_SEL_EXT_MODE = 10
        self.SHIFT_ALU_OP = 12
        self.SHIFT_JMP_TYPE = 15
        self.SHIFT_JMP_ADDR = 17

        self.mp_memory = {
            # FETCH
            0x00: self._microcode(
                {"read_mem": True, "latch_ir": True, "sel_mem_addr": "PC"}, self.SEQ_INC
            ),
            0x01: self._microcode(
                {
                    "sel_alu_l": "PC",
                    "sel_alu_r": "INC_PC",
                    "alu_op": "ADD",
                    "latch_pc": True,
                },
                self.SEQ_MAP,
            ),
            # LUI
            0x2: self._microcode(
                {
                    "sel_alu_r": "IMM",
                    "alu_op": "PASS_R",
                    "sel_reg_wr": "ALU",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_U,
            ),
            # MV
            0x3: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "alu_op": "PASS_L",
                    "sel_reg_wr": "ALU",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # SW
            0x4: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "IMM",
                    "alu_op": "ADD",
                    "sel_mem_addr": "ALU",
                    "write_mem": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_16,
            ),
            # LW
            0x5: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "IMM",
                    "alu_op": "ADD",
                    "sel_mem_addr": "ALU",
                    "read_mem": True,
                    "sel_reg_wr": "MEM",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_16,
            ),
            # ADDI
            0x6: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "IMM",
                    "alu_op": "ADD",
                    "write_reg": True,
                    "sel_reg_wr": "ALU",
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_12,
            ),
            # ADD
            0x7: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "RS2",
                    "alu_op": "ADD",
                    "sel_reg_wr": "ALU",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # SUB
            0x8: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "RS2",
                    "alu_op": "SUB",
                    "sel_reg_wr": "ALU",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # MUL
            0x9: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "RS2",
                    "alu_op": "MUL",
                    "sel_reg_wr": "ALU",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # AND
            0xA: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "RS2",
                    "alu_op": "AND",
                    "sel_reg_wr": "ALU",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # INV
            0xB: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "alu_op": "INV",
                    "sel_reg_wr": "ALU",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # J
            0xC: self._microcode(
                {
                    "sel_alu_r": "IMM",
                    "alu_op": "PASS_R",
                    "latch_pc": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_20,
            ),
            # JR
            0xD: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "alu_op": "PASS_L",
                    "latch_pc": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # JZ
            0xE: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "alu_op": "PASS_L",
                },
                self.SEQ_JMP_Z,
                jmp_addr=0x10,
            ),
            0xF: self._microcode({}, self.SEQ_JMP, jmp_addr=0x0),
            0x10: self._microcode(
                {
                    "sel_alu_r": "IMM",
                    "alu_op": "PASS_R",
                    "latch_pc": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_16,
            ),
            # HALT
            0x11: self._microcode({}, self.SEQ_JMP, jmp_addr=0x12),
        }

    def tick(self):
        if self.mPC == self.dispatch_table[opcode_to_binary[Opcode.HALT]]:
            raise StopIteration()

        instr = self.mp_memory.get(self.mPC, 0)

        signals = {
            "latch_pc": bool(instr & (1 << self.SHIFT_LATCH_PC)),
            "latch_ir": bool(instr & (1 << self.SHIFT_LATCH_IR)),
            "read_mem": bool(instr & (1 << self.SHIFT_READ_MEM)),
            "write_mem": bool(instr & (1 << self.SHIFT_WRITE_MEM)),
            "write_reg": bool(instr & (1 << self.SHIFT_WRITE_REG)),
            "sel_ext_mode": ["IMM_12", "IMM_20", "OFFSET_16", "IMM_U"][
                (instr >> self.SHIFT_SEL_EXT_MODE) & 0x3
            ],
            "sel_mem_addr": "PC" if (instr & (1 << self.SHIFT_SEL_MEM_ADDR)) else "ALU",
            "sel_reg_wr": "MEM" if (instr & (1 << self.SHIFT_SEL_REG_WR)) else "ALU",
            "sel_alu_l": "PC" if (instr & (1 << self.SHIFT_SEL_ALU_L)) else "RS1",
            "sel_alu_r": ["RS2", "IMM", "INC_PC"][
                (instr >> self.SHIFT_SEL_ALU_R) & 0x3
            ],
            "alu_op": ["ADD", "SUB", "AND", "INV", "PASS_L", "PASS_R", "MUL"][
                (instr >> self.SHIFT_ALU_OP) & 0x7
            ],
        }

        self.data_path.tick(signals)

        jmp_type = (instr >> self.SHIFT_JMP_TYPE) & 0x3
        jmp_addr = (instr >> self.SHIFT_JMP_ADDR) & 0x7F
        opcode = (self.data_path.IR >> 27) & 0x1F
        if jmp_type == self.SEQ_INC:
            self.mPC += 1
        elif jmp_type == self.SEQ_MAP:
            self.mPC = self.dispatch_table.get(opcode, 0)
        elif jmp_type == self.SEQ_JMP:
            self.mPC = jmp_addr
        elif jmp_type == self.SEQ_JMP_Z:
            if self.data_path.flags.get("Z", False):
                self.mPC = jmp_addr
            else:
                self.mPC += 1

    def _microcode(
        self, signals: dict[str, any], jmp_type, jmp_addr=0, ext_mode=0
    ) -> int:
        """
        Перевод из словаря в микрокод.
        Структура микрокода:
        0     -- latch_pc
        1     -- latch_ir
        2     -- read_mem
        3     -- write_mem
        4     -- write_reg
        5     -- sel_mem_addr
        6     -- sel_reg_wr
        7     -- sel_alu_l
        8-9   -- sel_alu_r
        10-11 -- sel_ext_mode
        12-14 -- alu_op
        15-16 -- jmp_type (inc, map, jmp, jmp_z)
        17-23 -- jmp_addr
        """
        self.bits = 0
        if signals.get("latch_pc"):
            self.bits |= 1 << self.SHIFT_LATCH_PC
        if signals.get("latch_ir"):
            self.bits |= 1 << self.SHIFT_LATCH_IR
        if signals.get("read_mem"):
            self.bits |= 1 << self.SHIFT_READ_MEM
        if signals.get("write_mem"):
            self.bits |= 1 << self.SHIFT_WRITE_MEM
        if signals.get("write_reg"):
            self.bits |= 1 << self.SHIFT_WRITE_REG
        if signals.get("sel_mem_addr") == "PC":
            self.bits |= 1 << self.SHIFT_SEL_MEM_ADDR
        if signals.get("sel_reg_wr") == "MEM":
            self.bits |= 1 << self.SHIFT_SEL_REG_WR

        alu_l = {"RS1": 0, "PC": 1}.get(signals.get("sel_alu_l", "RS1"), 0)
        alu_r = {"RS2": 0, "IMM": 1, "INC_PC": 2}.get(
            signals.get("sel_alu_r", "RS2"), 0
        )
        op = {
            "ADD": 0,
            "SUB": 1,
            "AND": 2,
            "INV": 3,
            "PASS_L": 4,
            "PASS_R": 5,
            "MUL": 6,
        }.get(signals.get("alu_op", "PASS_L"), 4)

        self.bits |= alu_l << self.SHIFT_SEL_ALU_L
        self.bits |= alu_r << self.SHIFT_SEL_ALU_R
        self.bits |= op << self.SHIFT_ALU_OP

        self.bits |= (ext_mode & 0x3) << self.SHIFT_SEL_EXT_MODE

        self.bits |= jmp_type << self.SHIFT_JMP_TYPE
        self.bits |= (jmp_addr & 0x7F) << self.SHIFT_JMP_ADDR
        return self.bits


def simulation(initial_mem: [int], input_token: [str], trace_regs: list[int] = None):
    memory = Memory(initial_mem, input_token)
    data_path = DataPath(memory)
    control_unit = ControlUnit(data_path)
    ticks = 0
    try:
        while True:
            control_unit.tick()
            ticks += 1

            if trace_regs is not None:
                pc_str = f"PC: 0x{data_path.PC:02X}"
                mpc_str = f"mPC: 0x{control_unit.mPC:02X}"
                opcode = binary_to_opcode[(data_path.IR >> 27) & 0x1F]
                flags_str = f"Z: {data_path.flags['Z']} N: {data_path.flags['N']}"

                regs_str = " | ".join(
                    [f"R{r}: 0x{data_path.reg_file.read_rs(r):08X}" for r in trace_regs]
                )

                trace_line = f"Tick: {ticks:04d} | {pc_str:9} | {mpc_str:9} | {opcode:>4} | {flags_str} | {regs_str}"
                logging.debug("%s", trace_line)
    except StopIteration:
        pass
    print(f"\nTicks executed: {ticks}")
    print("Output:")
    print("".join(memory.output_buffer))


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
    parser.add_argument("source_file", nargs="?", default="./examples/hello/hello.bin")
    parser.add_argument("input_file", nargs="?", default="./examples/hello/hello.txt")
    parser.add_argument("--trace", nargs="+", type=int)

    args = parser.parse_args()
    main(args.source_file, args.input_file, args.trace)
