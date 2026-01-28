"""Wake word detection module."""

from .detector import WakeWordDetector


def create_engine(engine_type: str = "openwakeword"):
    """Factory function to create wake word engine.

    Args:
        engine_type: Type of engine ("openwakeword")

    Returns:
        WakeWordEngine instance or None if unavailable
    """
    if engine_type == "openwakeword":
        from .openwakeword import OpenWakeWordEngine
        return OpenWakeWordEngine()
    raise ValueError(f"Unknown wake word engine: {engine_type}")


__all__ = ["WakeWordDetector", "create_engine"]
