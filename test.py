from grammar import Grammar


class IntArray(Grammar):
    int = r(r'\d+')
    ws = r(r'\s*')
    item = d(ws) + (int | array) + d(ws)
    array = d(ws) + "[" + i(item)[None] + "]" + d(ws)


print(next(IntArray.array.parse("[1 [5 7] 7 [[[]]]]"))[0])
