from `21.py` import AnsiRenderer

def test():
    r = AnsiRenderer(10, 5)
    r.feed("\x1b[2J\x1b[1;1HHELLO\x1b[2;3HWORLD")
    for row in r.grid:
        print("'" + "".join(row) + "'")

if __name__ == "__main__":
    test()
