sub x0, x0, x0
sub x1, x1, x1
sub x4, x4, x4
sub sp, sp, sp
sub rp, rp, rp
addi sp, sp, 1791
addi rp, rp, 2047
addi x0, x0, 428
addi x4, x4, 16
NEXT:
lw x2, 0(x0)
addi x0, x0, 4
jr x2
DOCOL:
addi rp, rp, -4
sw x0, 0(rp)
addi x0, x2, 4
j NEXT
EXIT:
lw x0, 0(rp)
addi rp, rp, 4
j NEXT
ADD:
lw x2, 0(sp)
addi sp, sp, 4
lw x3, 0(sp)
add x2, x2, x3
sw x2, 0(sp)
j NEXT
SUB:
lw x2, 0(sp)
addi sp, sp, 4
lw x3, 0(sp)
sub x2, x3, x2
sw x2, 0(sp)
j NEXT
MUL:
lw x2, 0(sp)
addi sp, sp, 4
lw x3, 0(sp)
mul x2, x2, x3
sw x2, 0(sp)
j NEXT
AND:
lw x2, 0(sp)
addi sp, sp, 4
lw x3, 0(sp)
and x2, x2, x3
sw x2, 0(sp)
j NEXT
NOT:
lw x2, 0(sp)
inv x2, x2
sw x2, 0(sp)
j NEXT
DUP:
lw x2, 0(sp)
addi sp, sp, -4
sw x2, 0(sp)
j NEXT
DROP:
addi sp, sp, 4
j NEXT
LIT:
lw x2, 0(x0)
addi x0, x0, 4
addi sp, sp, -4
sw x2, 0(sp)
j NEXT
SWAP:
lw x2, 0(sp)
lw x3, 4(sp)
sw x2, 4(sp)
sw x3, 0(sp)
j NEXT
STORE:
lw x2, 0(sp)
addi sp, sp, 4
lw x3, 0(sp)
addi sp, sp, 4
sw x3, 0(x2)
j NEXT
LOAD:
lw x2, 0(sp)
lw x3, 0(x2)
sw x3, 0(sp)
j NEXT
READ:
sub x2, x2, x2
addi x2, x2, 0x5F8
lw x3, 0(x2)
addi sp, sp, -4
sw x3, 0(sp)
j NEXT
PRINT:
sub x2, x2, x2
addi x2, x2, 0x5FC
lw x3, 0(sp)
addi sp, sp, 4
sw x3, 0(x2)
j NEXT
JNZ:
lw x2, 0(sp)
addi sp, sp, 4
jz x2, SKIP_JNZ
lw x0, 0(x0)
j NEXT
SKIP_JNZ:
addi x0, x0, 4
j NEXT
EZ:
lw x2, 0(sp)
addi sp, sp, 4
jz x2, DO_NEXT_Z
addi x0, x0, 4
DO_NEXT_Z:
j NEXT
GZ:
lw x2, 0(sp)
addi sp, sp, 4
jz x2, DO_SKIP_GZ
lui x3, 0xFFFFF
and x2, x2, x3
jz x2, DO_NEXT_GZ
DO_SKIP_GZ:
addi x0, x0, 4
DO_NEXT_GZ:
j NEXT
CELLS:
lw x2, 0(sp)
mul x2, x2, 4
sw x2, 0(sp)
j NEXT
EXECUTE:
lw x1, 0(sp)
addi sp, sp, 4
addi rp, rp, -4
sw x0, 0(rp)
mv x0, x1
j NEXT
HALT:
halt
START:
0xb0
4
0x180
FIB_STEP:
j DOCOL
0x28
0x1c
MAIN:
j DOCOL
0xb0
0
0xb0
1
0x1b8
0x1b8
0x1b8
0x1b8
0xb0
0x0
0xd8
0xb0
0x0
0xf0
0x118
0x1c
0x1c4
0x1a8
