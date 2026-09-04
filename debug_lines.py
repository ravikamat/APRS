with open('core/gate_engine.py', 'r') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

for i, line in enumerate(lines):
    stripped = line.strip()
    if line.strip().startswith('try:'):
        print(f'Line {i+1}: try')
    if line.strip().startswith('except'):
        print(f'Line {i+1}: except')
    if 'async def run_full_pipeline' in line:
        print(f'Line {i+1}: run_full_pipeline starts')
        break