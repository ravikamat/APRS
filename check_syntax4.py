import ast
import sys

with open('core/gate_engine.py', 'r') as f:
    content = f.read()

try:
    ast.parse(content)
    print('AST parse OK')
except SyntaxError as e:
    print(f'SyntaxError: {e}')
    print(f'Line {e.lineno}: {e.text}')
    with open('core/gate_engine.py', 'r') as f:
        lines = f.readlines()
    start = max(0, e.lineno - 5)
    end = min(len(open('core/gate_engine.py').readlines()), e.lineno + 5)
    for i in range(start, end):
        print(f'{e.lineno - 5 + i}: {repr(open("core/gate_engine.py").readlines()[i])}')