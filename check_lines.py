with open('core/gate_engine.py', 'r') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

for i, line in enumerate(lines):
    if 'try:' in line and 'except' not in line and 'finally' not in line:
        print(f'Line {i+1}: try')
    if line.strip().startswith('except'):
        print(f'Line {i+1}: except')
    if 'async def run_full_pipeline' in line:
        print(f'Line {i+1}: run_full_pipeline starts')
        break