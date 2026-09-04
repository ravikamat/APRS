with open('core/gate_engine.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines[960:990], 961):
    if line.strip() == ')':
        print(f'Line {i+960}: {repr(line)}')

PYEOF