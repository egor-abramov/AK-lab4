import io

var len
var i
var j
var s1
var s2

128 array d

: swap_elements
    d j @ cells + @ s1 !
    d j @ 1 + cells + @ s2 !
    s2 @ d j @ cells + !
    s1 @ d j @ 1 + cells + !
;

: inner_sort_loop
    0 j !
    loop
        d j @ cells + @
        d j @ 1 + cells + @
        - >0 if
            swap_elements
        then

        j @ 1 + j !
        len @ i @ - 1 - j @ -
    endloop
;

: bubble_sort
    0 i !
    loop
        len @ i @ - 1 - >0 if
            inner_sort_loop
        then

        i @ 1 + i !
        len @ 1 - i @ -
    endloop
;

d read_array
len !
len @ 1 - >0 if
    bubble_sort
then
d len @ print_array