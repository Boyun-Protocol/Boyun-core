"""Read one explicitly named dotenv secret without bulk import or execution."""
import os
import re
import stat

MAX_ENV_BYTES = 65536


def load_env_key(path, name='TYPESAFE_API_KEY'):
    """Return a single printable key; never export it or echo parse failures.

    Other entries are ignored, including their values. Quotes around the chosen
    value are permitted, but expansions, escapes and command syntax are not.
    """
    if type(name) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', name):
        raise ValueError('invalid explicit environment key name')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ENV_BYTES:
                raise ValueError('bounded regular environment file required')
            raw = handle.read(MAX_ENV_BYTES + 1)
        if len(raw) > MAX_ENV_BYTES:
            raise ValueError('environment file exceeds byte budget')
        text = raw.decode('utf-8')
        found = []
        for line in text.splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?' + re.escape(name) + r'\s*=\s*(.*?)\s*', line)
            if match:
                value = match.group(1)
                if value.startswith(('"', "'")):
                    if len(value) < 2 or value[-1] != value[0]:
                        raise ValueError('malformed named environment value')
                    value = value[1:-1]
                if (not value or len(value) > 4096 or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
                    or any(char in value for char in '$`\\\'"')):
                    raise ValueError('invalid named environment key')
                found.append(value)
        if len(found) != 1:
            raise ValueError('exactly one named environment key required')
        return found[0]
    except (OSError, UnicodeError, TypeError) as error:
        raise ValueError('cannot read the explicitly named key from a bounded regular environment file') from None
