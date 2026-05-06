# x0 -- IP
# rp -- Return Stack Pointer
# sp -- Data Stack Pointer

#############################

NEXT:
    lw t0, 0(x0)
    addi x0, x0, 4
    jr t0

#############################

DOCOL:
    addi rp, rp, -4
    sw x0, 0(rp)
    addi x0, t0, 4
    j NEXT

#############################

EXIT:
    lw x0, 0(rp)
    addi rp, rp, 4
    j NEXT

#############################

# Primitives

##############################

ADD:
    lw t0, 0(sp)
    addi sp, sp, 4
    lw t1, 0(sp)
    add t0, t0, t1
    sw t0, 0(sp)
    j NEXT

##############################

SUB:
    lw t0, 0(sp)
    addi sp, sp, 4
    lw t1, 0(sp)
    sub t0, t1, t0
    sw t0, 0(sp)
    j NEXT

##############################

MUL:
    lw t0, 0(sp)
    addi sp, sp, 4
    lw t1, 0(sp)
    mul t0, t0, t1
    sw t0, 0(sp)
    j NEXT

##############################

AND:
    lw t0, 0(sp)
    addi sp, sp, 4
    lw t1, 0(sp)
    and t0, t0, t1
    sw t0, 0(sp)
    j NEXT

##############################

NOT:
    lw t0, 0(sp)
    inv t0, t0
    sw t0, 0(sp)
    j NEXT

##############################

DUP:
    lw t0, 0(sp)
    addi sp, sp, -4
    sw t0, 0(sp)
    j NEXT

##############################

DROP:
    addi sp, sp, 4
    j NEXT

##############################

LIT:
    lw t0, 0(x0)
    addi x0, x0, 4
    addi sp, sp, -4
    sw t0, 0(sp)
    j NEXT

##############################

SWAP:
    lw t0, 0(sp)
    lw t1, 4(sp)
    sw t0, 4(sp)
    sw t1, 0(sp)
    j NEXT

##############################

STORE:
    lw t0, 0(sp)
    addi sp, sp, 4
    lw t1, 0(sp)
    addi sp, sp, 4
    sw t1, 0(t0)
    j NEXT

##############################

LOAD:
    lw t0, 0(sp)
    lw t1, 0(t0)
    sw t1, 0(sp)
    j NEXT

##############################

READ:
    addi t0, zero, 0x5F8  # load input port address
    lw t1, 0(t0)
    addi sp, sp, -4
    sw t1, 0(sp)
    j NEXT

##############################

PRINT:
    addi t0, zero, 0x5FC  # load output port address

    lw t1, 0(sp)
    addi sp, sp, 4
    sw t1, 0(t0)
    j NEXT

##############################

JNZ:
    lw t0, 0(sp)
    addi sp, sp, 4
    jz t0, SKIP_JNZ
    lw x0, 0(x0)
    j NEXT
SKIP_JNZ:
    addi x0, x0, 4
    j NEXT

##############################

EZ:
    lw t0, 0(sp)
    addi sp, sp, 4
    jz t0, DO_NEXT_Z
    addi x0, x0, 4
DO_NEXT_Z:
    j NEXT

##############################

GZ:
    lw t0, 0(sp)
    addi sp, sp, 4
    jz t0, DO_SKIP_GZ
    lui t1, 0x80000
    and t1, t0, t1
    jz t1, DO_NEXT_GZ
DO_SKIP_GZ:
    addi x0, x0, 4
DO_NEXT_GZ:
    j NEXT

##############################

CELLS:
    lw t0, 0(sp)
    addi t1, zero, 4
    mul t0, t0, t1
    sw t0, 0(sp)
    j NEXT

##############################

EXECUTE:
    lw t0, 0(sp)
    addi sp, sp, 4

    addi rp, rp, -4
    sw x0, 0(rp)

    mv x0, t0
    j NEXT

##############################

PRINT_STR:
    lw t0, 0(sp)         # start addr
    addi sp, sp, 4
    lw t1, 0(t0)         # str len
    addi t2, zero, 0x5FC # output addr

PRINT_STR_LOOP:
    jz t1, PRINT_STR_END
    addi t0, t0, 4
    lw t3, 0(t0)
    sw t3, 0(t2)
    addi t1, t1, -1
    j PRINT_STR_LOOP
PRINT_STR_END:
    j NEXT

##############################

READ_STR:
    lw t0, 0(sp)            # start addr
    addi sp, sp, 4
    mv t1, t0               # current pointer
    addi t2, zero, 0x5F8    # input addr
    addi t3, zero, 0        # str len

READ_STR_LOOP:
    lw t4, 0(t2)
    addi t4, t4, -10
    jz t4, READ_STR_END
    addi t4, t4, 10

    addi t1, t1, 4
    sw t4, 0(t1)
    addi t3, t3, 1
    j READ_STR_LOOP

READ_STR_END:
    sw t3, 0(t0)
    j NEXT

##############################

HALT:
    halt

##############################
