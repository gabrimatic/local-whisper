"""Allow running as: python -m whisper_voice"""

import sys

if getattr(sys, 'frozen', False):
    from whisper_voice.app import service_main
    if __name__ == "__main__":
        service_main()
else:
    from .cli import cli_main
    if __name__ == "__main__":
        cli_main()
