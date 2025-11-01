"""
Language loader - automatically loads and registers all available language configurations
"""
import logging

logger = logging.getLogger(__name__)


def load_all_languages():
    """
    Load all available language configurations

    This function imports all language modules, which automatically
    register themselves via the register_language() function.
    """
    try:
        # Import language modules - they will auto-register
        from . import en  # English
        from . import pl  # Polish

        logger.info("Loaded languages: en (English), pl (Polish)")

    except ImportError as e:
        logger.error(f"Failed to load language configuration: {e}")
        raise


# Auto-load languages when this module is imported
load_all_languages()
