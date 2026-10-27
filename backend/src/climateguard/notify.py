"""Alert delivery: one SNS publish per language topic for the city.

Each subscriber gets the message in the language they signed up with. SNS adds an
unsubscribe link to the bottom of every email. NOTIFY_MODE=dryrun writes to the
local outbox instead (backend/.local/outbox.jsonl).
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config
from .cities import CITIES, TIMEZONE
from .subscriptions import LANGS, outbox, topic_arn

log = logging.getLogger(__name__)
_TZ = ZoneInfo(TIMEZONE)

# SNS email subjects: kept ASCII (no accents/diacritics) for safety, under 100 chars.
HAZARD_SUBJECT = {
    "en": {"heat": "heat", "smoke": "smoke", "flood": "flood", "wind": "wind", "cold": "cold",
           "fog": "fog", "other": "safety"},
    "es": {"heat": "calor", "smoke": "humo", "flood": "inundacion", "wind": "viento", "cold": "frio",
           "fog": "niebla", "other": "seguridad"},
    "vi": {"heat": "nang nong", "smoke": "khoi", "flood": "lu lut", "wind": "gio manh", "cold": "lanh",
           "fog": "suong mu", "other": "an toan"},
}
SUBJECT = {
    "en": "ClimateGuard {sev} {hazard} alert - {city}",
    "es": "ClimateGuard: alerta de {hazard} - {city}",
    "vi": "ClimateGuard: canh bao {hazard} - {city}",
}
FOOTER = {
    "en": ("ClimateGuard alert for {city}, sent {time}.\nMore info: {url}\n"
           "This is safety information, not medical advice. In an emergency, call 911.\n"
           "To stop these alerts, use the unsubscribe link at the bottom of this email."),
    "es": ("Alerta de ClimateGuard para {city}, enviada {time}.\nMás información: {url}\n"
           "Esta es información de seguridad, no consejo médico. En una emergencia, llame al 911.\n"
           "Para dejar de recibir estas alertas, use el enlace para cancelar la suscripción "
           "al final de este correo."),
    "vi": ("Cảnh báo ClimateGuard cho {city}, gửi lúc {time}.\nThêm thông tin: {url}\n"
           "Đây là thông tin an toàn, không phải lời khuyên y tế. Trường hợp khẩn cấp, hãy gọi 911.\n"
           "Để ngừng nhận cảnh báo, hãy bấm vào liên kết hủy đăng ký ở cuối email này."),
}


def compose(city: str, lang: str, hazard: str, severity: str, message: str) -> tuple[str, str]:
    name = CITIES[city]["name"]
    subject = SUBJECT[lang].format(sev=severity.upper(), hazard=HAZARD_SUBJECT[lang].get(hazard, hazard),
                                   city=name)[:99]
    url = f"{config.FRONTEND_URL}/?city={city}&lang={lang}"
    when = datetime.now(_TZ).strftime("%Y-%m-%d %H:%M")
    body = f"{message}\n\n--\n" + FOOTER[lang].format(city=name, time=when, url=url)
    return subject, body


def deliver(city: str, hazard: str, severity: str, messages: dict) -> dict:
    published = []
    for lang in LANGS:
        subject, body = compose(city, lang, hazard, severity, messages[lang])
        if config.NOTIFY_MODE == "sns":
            import boto3

            boto3.client("sns").publish(TopicArn=topic_arn(city, lang), Subject=subject, Message=body)
        else:
            outbox({"type": "alert", "city": city, "lang": lang, "subject": subject, "body": body})
        published.append(lang)
    log.info("delivered %s %s alert for %s via %s: %s", severity, hazard, city, config.NOTIFY_MODE, published)
    return {"channel": config.NOTIFY_MODE, "languages": published}
