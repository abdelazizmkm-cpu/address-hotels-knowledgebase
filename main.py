"""Entry point — delegates to typesense/main.py."""
import subprocess
import sys

if __name__ == '__main__':
    subprocess.run(
        [sys.executable, '-X', 'utf8', 'typesense/main.py'] + sys.argv[1:],
        check=True,
    )
