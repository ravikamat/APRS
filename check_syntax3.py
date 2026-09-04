import sys
with open('core/gate_engine.py', 'r') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

# Find the extra ')'
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped == ')' and i > 900:
        print(f'Line {i+1}: {repr(line)}')

# Check syntax
import ast
try:
    with open('core/gate_engine.py', 'r') as f:
        content = f.read()
    ast.parse(content)
    print('AST parse OK')
except SyntaxError as e:
    print(f'SyntaxError: {e}')
    print(f'Line {e.lineno}: {e.text}')
    with open('core/gate_engine.py', 'r') as f:
        lines = f.readlines()
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
        print(f'{e.lineno-2+i}: {repr(lines[e.lineno-3+i])}')