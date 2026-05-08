from isa import Opcode, opcode_to_binary


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
        self, mem_size: int = 2048, input_addr: int = 0x5F8, output_addr: int = 0x5FC
    ):
        self.INPUT_ADDR = input_addr
        self.OUTPUT_ADDR = output_addr
        self.MEM_SIZE = mem_size
        self.mem = [0] * self.MEM_SIZE
        self.input_buffer = []

    def read(self, addr: int) -> int:
        if addr == self.INPUT_ADDR:
            return self.input_buffer.pop(0)
        elif 0 <= addr < self.MEM_SIZE and addr != self.OUTPUT_ADDR:
            return self.mem[addr]
        raise Exception(f"Invalid memory access at address {addr}")

    def write(self, val: int, addr: int):
        if addr == self.OUTPUT_ADDR:
            print(val)
        elif 0 <= addr < self.MEM_SIZE and addr != self.INPUT_ADDR:
            self.mem[addr] = val
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
            self.memory.write(rs1_data, mem_addr)

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
            n = 12
        elif mode == "IMM_20":
            n = 20
        elif mode == "OFFSET_16":
            n = 16
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
            opcode_to_binary[Opcode.LW]: 0x6,
            opcode_to_binary[Opcode.ADDI]: 0x9,
            opcode_to_binary[Opcode.ADD]: 0xA,
            opcode_to_binary[Opcode.SUB]: 0xB,
            opcode_to_binary[Opcode.MUL]: 0xC,
            opcode_to_binary[Opcode.AND]: 0xD,
            opcode_to_binary[Opcode.INV]: 0xE,
            opcode_to_binary[Opcode.J]: 0xF,
            opcode_to_binary[Opcode.JR]: 0x10,
            opcode_to_binary[Opcode.JZ]: 0x11,
            opcode_to_binary[Opcode.HALT]: 0x15,
        }

        # Типы переходов после исполнения микрокоманды
        self.SEQ_INC = 0  # pc + 4
        self.SEQ_MAP = 1  # dispatch
        self.SEQ_JMP = 2  # безусловный
        self.SEQ_JMP_Z = 3  # условный (z == 0)

        # Режимы расширения знака
        EXT_MODE_12 = 0
        EXT_MODE_20 = 1
        EXT_MODE_16 = 2

        # TODO: translate asm to mc
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
                    "self_alu_r": "IMM",
                    "alu_op": "PASS_R",
                    "sel_reg_wr": "ALU",
                    "reg_write": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_20,
            ),
            # MV
            0x3: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "alu_op": "PASS_L",
                    "sel_reg_wr": "ALU",
                    "reg_write": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # SW
            0x4: self._microcode(
                {"sel_alu_l": "RS1", "sel_alu_r": "IMM", "alu_op": "ADD"},
                self.SEQ_INC,
                ext_mode=EXT_MODE_16,
            ),
            0x5: self._microcode(
                {
                    "sel_mem_addr": "ALU",
                    "write_mem": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # LW
            0x6: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "IMM",
                    "alu_op": "ADD",
                },
                self.SEQ_INC,
                ext_mode=EXT_MODE_16,
            ),
            0x7: self._microcode(
                {
                    "sel_mem_addr": "ALU",
                    "read_mem": True,
                },
                self.SEQ_INC,
            ),
            0x8: self._microcode(
                {
                    "sel_reg_wr": "MEM",
                    "write_reg": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # ADDI
            0x9: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "sel_alu_r": "IMM",
                    "alu_op": "ADD",
                    "write_reg": True,
                    "sel_reg_write": "ALU",
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_12,
            ),
            # ADD
            0xA: self._microcode(
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
            0xB: self._microcode(
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
            0xC: self._microcode(
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
            0xD: self._microcode(
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
            0xE: self._microcode(
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
            0xF: self._microcode(
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
            0x10: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "alu_op": "PASS_L",
                    "latch_pc": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
            ),
            # JZ
            0x11: self._microcode(
                {
                    "sel_alu_l": "RS1",
                    "alu_op": "PASS_L",
                },
                self.SEQ_INC,
            ),
            0x12: self._microcode({}, self.SEQ_JMP_Z, jmp_addr=0x14),
            0x13: self._microcode({}, self.SEQ_JMP, 0x0),
            0x14: self._microcode(
                {
                    "sel_alu_r": "IMM",
                    "alu_op": "PASS_R",
                    "latch_pc": True,
                },
                self.SEQ_JMP,
                jmp_addr=0x0,
                ext_mode=EXT_MODE_20,
            ),
            # HALT
            0x15: self._microcode({}, self.SEQ_JMP, jmp_addr=0x15),
        }

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

    def tick(self):
        instr = self.mp_memory.get(self.mPC, 0)

        signals = {
            "latch_pc": bool(instr & (1 << self.SHIFT_LATCH_PC)),
            "latch_ir": bool(instr & (1 << self.SHIFT_LATCH_IR)),
            "read_mem": bool(instr & (1 << self.SHIFT_READ_MEM)),
            "write_mem": bool(instr & (1 << self.SHIFT_WRITE_MEM)),
            "write_reg": bool(instr & (1 << self.SHIFT_WRITE_REG)),
            "sel_ext_mode": ["IMM_12", "IMM_20", "OFFSET_16"][
                (instr >> self.SHIFT_SEL_EXT_MODE) & 0x3
            ],
            "sel_mem_addr": "PC" if (instr & (1 << self.SHIFT_SEL_MEM_ADDR)) else "ALU",
            "sel_reg_wr": "MEM" if (instr & (1 << self.SHIFT_SEL_REG_WR)) else "ALU",
            "sel_alu_l": ["RS1", "PC"][(instr >> self.SHIFT_SEL_ALU_L) & 0x3],
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


if __name__ == "__main__":
    ...
