var n
var temp
var reversed
var a
var b
var prod
var max_pal
var cont_b

: is_palindrome
    prod @ temp !
    0 reversed !

    loop
        temp @ 10 % n !
        temp @ 10 / temp !
        reversed @ 10 * n @ + reversed !
        temp @
    endloop

    prod @ reversed @ - =0
;

: eval_pair
    a @ b @ * prod !

    prod @ max_pal @ - >0 if
        is_palindrome if
            prod @ max_pal !
        then
        1 cont_b !
    else
        0 cont_b !
    then
;

: loop_b
    a @ b !
    loop
        eval_pair
        b @ 1 - b !

        b @ 99 - >0
        cont_b @ *
    endloop
;

: loop_a
    999 a !
    loop
        loop_b
        a @ 1 - a !

        a @ 99 - >0
    endloop
;

0 max_pal !
loop_a
max_pal @ .