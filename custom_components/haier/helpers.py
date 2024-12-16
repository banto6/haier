def try_read_as_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value == 'true'

    raise ValueError('[{}]无法被转为bool'.format(value))

def equals_ignore_case(value, target):
    if isinstance(value, str) and isinstance(target, str):
        return value.lower() == target.lower()

    return value == target

def contains_any_ignore_case(value, targets: list):
    for target in targets:
        if equals_ignore_case(value, target):
            return True

    return False