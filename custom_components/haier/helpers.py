

def try_read_as_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value == 'true'

    raise ValueError('[{}]无法被转为bool'.format(value))
