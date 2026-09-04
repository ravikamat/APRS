with open('core/gate_engine.py', 'r') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

outer_try_line = 0
outer_except_line = 0
inner_try_line = 0
inner_except_line = 0
run_full_pipeline_line = 0

for i, line in enumerate(lines):
    stripped = line.strip()
    if line.strip().startswith('try:'):
        if outer_try_line == 0:
            outer_try_line = i + 1
            print(f'Outer try at line {i+1}')
        elif inner_try_line == 0:
            inner_try_line = i + 1
            print(f'Inner try at line {i+1}')
    if line.strip().startswith('except'):
        if outer_except_line == 0:
            outer_except_line = i + 1
            print(f'Outer except at line {i+1}')
        elif inner_except_line == 0:
            inner_except_line = i + 1
            print(f'Inner except at line {i+1}')
    if 'async def run_full_pipeline' in line:
        run_full_pipeline_line = i + 1
        print(f'run_full_pipeline starts at line {i+1}')
        break

print(f'Outer try at line {outer_try_line}')
print(f'Inner try at line {inner_try_line}')
print(f'Inner except at line {inner_except_line}')
print(f'Outer except at line {outer_except_line}')
print(f'run_full_pipeline starts at line {run_full_pipeline_line}')