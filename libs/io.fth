: emit 16128 ! ;
: cr 10 emit ;

var _str_ptr
var _str_len

: _print_char
    _str_ptr @ 4 + _str_ptr !
    _str_ptr @ @ emit
;

: _print_loop
    loop
        _print_char
        _str_len @ 1 - _str_len !
        _str_len @
    endloop
;

: print_str
    _str_ptr !
    _str_ptr @ @ _str_len !

    _str_len @ >0 if
        _print_loop
    then
;

var _start_ptr
var _char

: _process_char
    _char @
    _str_ptr @ dup 4 + _str_ptr ! !
    _str_len @ 1 + _str_len !
;

: read_str
    dup _start_ptr !
    4 + _str_ptr !
    0 _str_len !

    loop
        read _char !

        _char @ 10 - >0 if
            _process_char
        then

        _char @ 10 -
    endloop

    _str_len @ _start_ptr @ !
;

var _ch
var _acc
var _sign
var _is_reading
var _chars_read
var _arr_ptr
var _arr_len

: read_num
    0 _acc !
    0 _sign !
    0 _chars_read !

    read _ch !
    _ch @ 45 - =0 if
        1 _sign !
        read _ch !
    then

    loop
        1 _is_reading !
        _ch @ 32 - =0 if 0 _is_reading ! then
        _ch @ 10 - =0 if 0 _is_reading ! then

        _is_reading @ >0 if
            _acc @ 10 * _ch @ 48 - + _acc !
            _chars_read @ 1 + _chars_read !
            read _ch !
        then

        _is_reading @
    endloop

    _sign @ >0 if
        0 _acc @ - _acc !
    then

    _acc @
;

: read_array
    _arr_ptr !
    0 _arr_len !

    loop
        read_num

        _chars_read @ >0 if
            _arr_ptr @ _arr_len @ cells + !
            _arr_len @ 1 + _arr_len !
        else
            drop
        then

        _ch @ 10 -
    endloop

    _arr_len @
;

var _print_ptr
var _print_len
var _print_i

: _print_array_loop
    loop
        _print_ptr @ _print_i @ cells + @ .
        _print_i @ 1 + _print_i !
        _print_len @ _print_i @ -
    endloop
;

: print_array
    _print_len !
    _print_ptr !
    0 _print_i !

    _print_len @ >0 if
        _print_array_loop
    then
;