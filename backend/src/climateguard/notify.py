"""Alert delivery: one SNS publish per (zone, language) topic that has sign-ups.

Each subscriber gets the message in the language they signed up with. EN/ES/VI come from
the agent; other languages are machine-translated from English and labeled. SNS adds an
unsubscribe link to the bottom of every email. NOTIFY_MODE=dryrun writes to the local
outbox instead (backend/.local/outbox.jsonl).
"""
import logging
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config, hazards, units
from .languages import REVIEWED
from .subscriptions import outbox, topic_arn
from .translate import translate_alert

log = logging.getLogger(__name__)

# SNS email subjects: kept ASCII (no accents/diacritics) and under 100 characters.
# Languages without a Latin-script subject (zh, ko, ar) use the English one.
HAZARD_SUBJECT = {
    "en": {"heat": "heat", "cold": "cold", "winter": "winter storm", "flood": "flood", "coastal": "coastal",
           "tornado": "tornado watch", "thunderstorm": "thunderstorm", "tropical": "tropical storm",
           "wind": "wind", "fire": "fire weather", "smoke": "air quality", "dust": "dust", "fog": "fog",
           "other": "safety"},
    "es": {"heat": "calor", "cold": "frio", "winter": "tormenta invernal", "flood": "inundacion",
           "coastal": "costa", "tornado": "tornado", "thunderstorm": "tormentas", "tropical": "huracan",
           "wind": "viento", "fire": "incendios", "smoke": "calidad del aire", "dust": "polvo", "fog": "niebla",
           "other": "seguridad"},
    "vi": {"heat": "nang nong", "cold": "lanh", "winter": "bao tuyet", "flood": "lu lut", "coastal": "ven bien",
           "tornado": "loc xoay", "thunderstorm": "dong", "tropical": "bao", "wind": "gio manh",
           "fire": "chay rung", "smoke": "chat luong khong khi", "dust": "bui", "fog": "suong mu", "other": "an toan"},
    "tl": {"heat": "init", "cold": "lamig", "winter": "niyebe", "flood": "baha", "coastal": "baybayin",
           "tornado": "buhawi", "thunderstorm": "kulog at kidlat", "tropical": "bagyo", "wind": "hangin",
           "fire": "sunog", "smoke": "kalidad ng hangin", "dust": "alikabok", "fog": "hamog", "other": "kaligtasan"},
}
SUBJECT = {
    "en": "ClimateGuard {sev} {hazard} alert - {place}",
    "es": "ClimateGuard: alerta de {hazard} - {place}",
    "vi": "ClimateGuard: thong bao {hazard} - {place}",  # "thong bao" (notice): never an NWS level name
    "tl": "ClimateGuard: babala sa {hazard} - {place}",
}
FOOTER = {
    "en": ("ClimateGuard alert for {place}, sent {time}.\nMore info: {url}\n"
           "This is safety information, not medical advice. In an emergency, call 911.\n"
           "To stop these alerts, use the unsubscribe link at the bottom of this email."),
    "es": ("Alerta de ClimateGuard para {place}, enviada {time}.\nMás información: {url}\n"
           "Esta es información de seguridad, no consejo médico. En una emergencia, llame al 911.\n"
           "Para dejar de recibir estas alertas, use el enlace para cancelar la suscripción "
           "al final de este correo."),
    "vi": ("Cảnh báo ClimateGuard cho {place}, gửi lúc {time}.\nThêm thông tin: {url}\n"
           "Đây là thông tin an toàn, không phải lời khuyên y tế. Trường hợp khẩn cấp, hãy gọi 911.\n"
           "Để ngừng nhận cảnh báo, hãy bấm vào liên kết hủy đăng ký ở cuối email này."),
    # Automatic translations (labeled as such in every message)
    "zh": ("ClimateGuard 针对 {place} 的警报，发送时间：{time}。\n更多信息：{url}\n"
           "这是安全信息，不是医疗建议。紧急情况请拨打 911。\n"
           "如需停止接收这些警报，请使用本邮件底部的退订链接。"),
    "tl": ("Babala ng ClimateGuard para sa {place}, ipinadala {time}.\nKaragdagang impormasyon: {url}\n"
           "Ito ay impormasyong pangkaligtasan, hindi payong medikal. Sa emergency, tumawag sa 911.\n"
           "Para ihinto ang mga babalang ito, gamitin ang link para mag-unsubscribe sa ibaba ng email na ito."),
    "ko": ("{place}에 대한 ClimateGuard 경보, {time} 발송.\n자세한 정보: {url}\n"
           "이것은 안전 정보이며 의학적 조언이 아닙니다. 응급 상황에서는 911에 전화하세요.\n"
           "이 경보 수신을 중단하려면 이 이메일 하단의 구독 취소 링크를 사용하세요."),
    "ar": ("تنبيه ClimateGuard لمنطقة {place}، أُرسل في {time}.\nمزيد من المعلومات: {url}\n"
           "هذه معلومات سلامة وليست نصيحة طبية. في حالات الطوارئ اتصل بالرقم 911.\n"
           "لإيقاف هذه التنبيهات، استخدم رابط إلغاء الاشتراك في أسفل هذه الرسالة."),
}
AUTO_LABEL = {
    "zh": "（自动翻译）", "tl": "(Awtomatikong pagsasalin)", "ko": "(자동 번역)", "ar": "(ترجمة آلية)",
}
AUTO_FALLBACK = {  # shown when translation failed and the English text is sent instead
    "zh": "（翻译暂不可用，以下为英文原文）", "tl": "(Hindi available ang pagsasalin; nasa Ingles ang mensahe)",
    "ko": "(번역을 사용할 수 없어 영어 원문을 보냅니다)", "ar": "(الترجمة غير متاحة؛ الرسالة باللغة الإنجليزية)",
}
EXCLUSION_LINE = {
    "en": hazards.EXCLUSION_NOTE,
    "es": ("ClimateGuard no envía avisos de tornado, inundación repentina, tormenta eléctrica severa ni viento "
           "extremo: use las Alertas de Emergencia Inalámbricas de su teléfono y la radio meteorológica NOAA."),
    "vi": ("ClimateGuard không gửi cảnh báo lốc xoáy, lũ quét, dông bão nghiêm trọng hoặc gió cực mạnh: hãy dựa vào "
           "Cảnh báo Khẩn cấp Không dây trên điện thoại và Đài Thời tiết NOAA."),
}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def compose(zone: dict, lang: str, hazard: str, severity: str, message: str,
            translated: bool | None = None) -> tuple[str, str]:
    place = zone.get("place") or zone["name"]
    subj_lang = lang if lang in SUBJECT else "en"
    words = HAZARD_SUBJECT[subj_lang]
    subject = _ascii(SUBJECT[subj_lang].format(sev=severity.upper(), hazard=words.get(hazard, words["other"]),
                                               place=place))[:99]
    url = f"{config.FRONTEND_URL}/?zone={zone['zone']}&lang={lang}"
    when = datetime.now(ZoneInfo(zone.get("tz") or "America/New_York")).strftime("%Y-%m-%d %H:%M")
    head = units.format_temps(message, lang)  # translations too: °F (°C) for non-English
    if lang in AUTO_LABEL:
        head = f"{AUTO_LABEL[lang] if translated else AUTO_FALLBACK[lang]}\n{head}"
    footer = FOOTER[lang].format(place=place, time=when, url=url)
    note = EXCLUSION_LINE.get(lang, EXCLUSION_LINE["en"])
    return subject, f"{head}\n\n--\n{footer}\n{note}"


def deliver(zone: dict, hazard: str, severity: str, messages: dict) -> dict:
    """`messages` holds the agent's EN/ES/VI text. Publishes to every language with sign-ups
    in the zone (the reviewed three when there are none yet, e.g. demo zones)."""
    langs = zone.get("langs") or list(REVIEWED)
    published, translations = [], {}
    for lang in langs:
        if lang in messages:
            text, translated = messages[lang], None
        else:
            text, translated = translate_alert(messages["en"], lang)
            translations[lang] = "translated" if translated else "english_fallback"
        subject, body = compose(zone, lang, hazard, severity, text, translated)
        if config.NOTIFY_MODE == "sns":
            import boto3

            boto3.client("sns").publish(TopicArn=topic_arn(zone["zone"], lang), Subject=subject, Message=body)
        else:
            outbox({"type": "alert", "zone": zone["zone"], "lang": lang, "subject": subject, "body": body})
        published.append(lang)
    log.info("delivered %s %s alert for %s via %s: %s", severity, hazard, zone["zone"], config.NOTIFY_MODE,
             published)
    return {"channel": config.NOTIFY_MODE, "languages": published, **({"translations": translations}
                                                                      if translations else {})}
