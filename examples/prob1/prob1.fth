var n
var temp
var reversed
var is_pal_flag

var a
var b
var prod
var max_pal
var cont_b
var loop_cond

: set_pal_true
    1 is_pal_flag !
;

: is_palindrome
    prod @ temp !
    0 reversed !
    
    loop
        temp @ 10 % n !
        temp @ 10 / temp !
        
        reversed @ 10 * n @ + reversed !
        
        temp @
    endloop
    
    0 is_pal_flag !
    prod @ reversed @ - =0 set_pal_true
;

: update_max
    prod @ max_pal !
;

: try_palindrome
    is_palindrome
    is_pal_flag @ >0 update_max
;

: set_cont_b
    1 cont_b !
;

: eval_pair
    a @ b @ * prod !
    
    0 cont_b !
    prod @ max_pal @ - >0 set_cont_b

    cont_b @ >0 try_palindrome
;

: set_loop_cond_1
    1 loop_cond !
;

: loop_b
    a @ b !
    loop
        eval_pair
        
        b @ 1 - b !
        
        0 loop_cond !
        b @ 99 - >0 set_loop_cond_1

        cont_b @ loop_cond @ *
    endloop
;

: loop_a
    999 a !
    loop
        loop_b
        
        a @ 1 - a !
        
        0 loop_cond !
        a @ 99 - >0 set_loop_cond_1
        loop_cond @
    endloop
;

0 max_pal !
loop_a

max_pal @ .