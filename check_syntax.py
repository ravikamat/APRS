import sys
with open('core/gate_engine.py', 'r') as f:
    content = f.read()

try:
    import ast
    ast.parse(content)
    print('AST parse OK')
except SyntaxError as e:
    print(f'SyntaxError: {e}')
    print(f'Line {e.lineno}: {e.text}')
    with open('core/gate_engine.py', 'r') as f:
        lines = f.readlines()
    start = max(0, e.lineno - 10)
    end = min(len(lines), e.lineno + 10)
    for i in range(start, end):
        print(f'{e.lineno - 10 + i}: {repr(lines[e.lineno - 10 + i])}')