"""Run one controlled recovery trial, then repeated held-out risk/none trials."""
import subprocess
import sys


def main():
    for module, extra in [
        ('scripts.run_fault_recovery', []),
        ('scripts.run_repeats', ['--max-estimated-usd', '5']),
    ]:
        print(f'Starting {module}', flush=True)
        subprocess.run([sys.executable, '-m', module, *extra], check=True)


if __name__ == '__main__':
    main()
