"""Allow running as: python -m whisper_voice"""

import sys

if getattr(sys, 'frozen', False):
    # Running as bundled app (py2app)
    from whisper_voice.app import main
else:
    # Running as module (python -m whisper_voice)
    from .app import main

if __name__ == "__main__":
    main()
