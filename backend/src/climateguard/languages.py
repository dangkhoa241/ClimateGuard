"""Alert languages. EN/ES/VI are written directly by the alert agent (not machine-translated afterwards).
Vietnamese was reviewed for style by a native speaker; Spanish has not been reviewed by a native speaker yet.
The `reviewed` flag below means "written by the agent, not machine-translated afterwards", not "checked by a
native speaker". zh/tl/ko/ar are machine-translated from the validated English message and always labeled."""

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
