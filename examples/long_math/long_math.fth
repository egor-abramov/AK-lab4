import io
import utils

var AL
var AH
var BL
var BH
var RL
var RH
var a31
var b31
var r31
var carry_flag

: add64
    AL @ BL @ + RL !

    AL @ 2147483647 not and a31 !
    BL @ 2147483647 not and b31 !
    RL @ 2147483647 not and r31 !

    a31 @ b31 @ and
    a31 @ b31 @ or
    r31 @ not and
    or

    0 carry_flag !
    not >0 if
        1 carry_flag !
    then

    AH @ BH @ + carry_flag @ + RH !
;

: sub64
    BL @ not BL !
    BH @ not BH !

    add64

    RL @ AL !
    RH @ AH !
    1 BL !
    0 BH !

    add64
;

string "64-bit Addition\n" msg_add
string "64-bit Addition with carry\n" msg_add_c
string "64-bit Subtraction\n" msg_sub
string "64-bit Subtraction with borrow\n" msg_sub_b
string "High: " msg_h
string " Low: " msg_l

: print_res
    msg_h print_str
    RH @ .
    msg_l print_str
    RL @ .
    cr print_str
;

msg_add print_str
100 AL !   1 AH !
200 BL !   2 BH !
add64
print_res

msg_add_c print_str
-1 AL !    0 AH !
1 BL !     0 BH !
add64
print_res

msg_sub print_str
500 AL !   5 AH !
200 BL !   2 BH !
sub64
print_res

msg_sub_b print_str
0 AL !     5 AH !
1 BL !     2 BH !
sub64
print_res