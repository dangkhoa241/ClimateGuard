"""Alert languages. EN/ES/VI are written by the agent and human-reviewed; the others are
machine-translated from the validated English message and always labeled as such."""

LANGS = {
    "en": {"name": "English", "native": "English", "reviewed": True},
    "es": {"name": "Spanish", "native": "Español", "reviewed": True},
    "vi": {"name": "Vietnamese", "native": "Tiếng Việt", "reviewed": True},
    "zh": {"name": "Simplified Chinese", "native": "中文（简体）", "reviewed": False},
    "tl": {"name": "Tagalog", "native": "Tagalog", "reviewed": False},
    "ko": {"name": "Korean", "native": "한국어", "reviewed": False},
    "ar": {"name": "Arabic", "native": "العربية", "reviewed": False, "rtl": True},
}
REVIEWED = tuple(code for code, v in LANGS.items() if v["reviewed"])   # written by the agent
AUTO = tuple(code for code, v in LANGS.items() if not v["reviewed"])   # translated from English


def is_supported(lang: str) -> bool:
    return lang in LANGS
