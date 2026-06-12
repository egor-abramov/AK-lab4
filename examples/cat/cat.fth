import io

loop
    read
    dup 10 - =0

    if
        drop
        0
    else
        emit
        1
    then
endloop