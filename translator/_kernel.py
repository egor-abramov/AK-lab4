import re


def load_kernel(path: str, start_addr: hex = 0x0) -> (dict[str, hex], [str], hex):
    labels = {}
    code = []
    current_addr = start_addr
    label_pattern = re.compile(r'^([A-Z_a-z0-9]*):')
    instruction_pattern = re.compile(r'^([A-Z_a-z]+)')

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line: continue

            label_match = label_pattern.match(line)
            if label_match:
                label_name = label_match.group(1)
                labels[label_name] = hex(current_addr)

                line = line[label_match.end():].strip()
                code.append(f"{label_name}:")

            if instruction_pattern.match(line):
                current_addr += 4
                code.append(line)

    return labels, code, current_addr
