"""Fixed data for the recovery agent, keyed by disaster type. Nothing here is written by a model.

The model only chooses from these lists: which damage concepts SAM 3.1 should outline in each photo, and
which follow-up questions to ask. Every label, question, answer choice and danger line shown to the person
comes from here. EN/ES/VI follow the reviewed style; zh/tl/ko/ar are labeled automatic in the app.
Disaster-agnostic by design: flood is one type among six.
"""

DISASTERS = ("flood", "wildfire", "earthquake", "storm", "heat_outage", "other")

DISASTER_LABELS = {
    "flood": {"en": "Flood", "es": "Inundación", "vi": "Lũ lụt", "zh": "洪水", "tl": "Baha", "ko": "홍수",
              "ar": "فيضان"},
    "wildfire": {"en": "Wildfire or smoke", "es": "Incendio forestal o humo", "vi": "Cháy rừng hoặc khói",
                 "zh": "野火或烟雾", "tl": "Sunog sa gubat o usok", "ko": "산불 또는 연기", "ar": "حريق غابات أو دخان"},
    "earthquake": {"en": "Earthquake", "es": "Terremoto", "vi": "Động đất", "zh": "地震", "tl": "Lindol",
                   "ko": "지진", "ar": "زلزال"},
    "storm": {"en": "Storm or tornado damage", "es": "Daños por tormenta o tornado", "vi": "Thiệt hại do bão hoặc lốc xoáy",
              "zh": "风暴或龙卷风损坏", "tl": "Pinsala ng bagyo o buhawi", "ko": "폭풍 또는 토네이도 피해",
              "ar": "أضرار عاصفة أو إعصار"},
    "heat_outage": {"en": "Heat or power outage", "es": "Calor o corte de luz", "vi": "Nắng nóng hoặc mất điện",
                    "zh": "高温或停电", "tl": "Init o brownout", "ko": "폭염 또는 정전", "ar": "حر شديد أو انقطاع الكهرباء"},
    "other": {"en": "Other", "es": "Otro", "vi": "Khác", "zh": "其他", "tl": "Iba pa", "ko": "기타", "ar": "أخرى"},
}

# SAM 3.1 takes one short noun phrase per request ($0.0025 each). `sam` is the phrase sent; labels are shown.
# Things work better than adjectives: live, "damaged drywall" found nothing on walls stripped to the studs.
CONCEPTS = {
    "water_line": {"sam": "water stain", "en": "Water line or stain", "es": "Marca o mancha de agua",
                   "vi": "Vệt nước", "zh": "水渍线", "tl": "Marka ng tubig", "ko": "물 자국", "ar": "أثر الماء"},
    "standing_water": {"sam": "standing water", "en": "Standing water", "es": "Agua estancada", "vi": "Nước đọng",
                       "zh": "积水", "tl": "Nakatigil na tubig", "ko": "고인 물", "ar": "مياه راكدة"},
    "mud": {"sam": "mud", "en": "Mud", "es": "Lodo", "vi": "Bùn", "zh": "淤泥", "tl": "Putik", "ko": "진흙",
            "ar": "طين"},
    "mold": {"sam": "mold", "en": "Mold", "es": "Moho", "vi": "Nấm mốc", "zh": "霉菌", "tl": "Amag", "ko": "곰팡이",
             "ar": "عفن"},
    "drywall": {"sam": "exposed wall studs", "en": "Wall opened to the studs", "es": "Pared abierta hasta la estructura",
                "vi": "Tường bị lột trơ khung", "zh": "墙面拆到龙骨", "tl": "Pader na tinanggalan hanggang sa poste",
                "ko": "골조가 드러난 벽", "ar": "جدار مكشوف حتى الهيكل"},
    "debris": {"sam": "debris", "en": "Debris", "es": "Escombros", "vi": "Mảnh vụn", "zh": "碎片杂物",
               "tl": "Mga kalat at pira-piraso", "ko": "잔해", "ar": "حطام"},
    "furniture": {"sam": "damaged furniture", "en": "Damaged furniture", "es": "Muebles dañados",
                  "vi": "Đồ đạc hư hại", "zh": "受损家具", "tl": "Sirang muwebles", "ko": "손상된 가구",
                  "ar": "أثاث متضرر"},
    "burned": {"sam": "burned wood", "en": "Burned area", "es": "Zona quemada", "vi": "Chỗ bị cháy", "zh": "烧毁部分",
               "tl": "Nasunog na bahagi", "ko": "불탄 부분", "ar": "منطقة محترقة"},
    "soot": {"sam": "soot", "en": "Soot", "es": "Hollín", "vi": "Muội than", "zh": "烟灰", "tl": "Uling", "ko": "그을음",
             "ar": "سخام"},
    "ash": {"sam": "ash", "en": "Ash", "es": "Ceniza", "vi": "Tro", "zh": "灰烬", "tl": "Abo", "ko": "재",
            "ar": "رماد"},
    "crack": {"sam": "crack", "en": "Crack", "es": "Grieta", "vi": "Vết nứt", "zh": "裂缝", "tl": "Bitak", "ko": "균열",
              "ar": "شق"},
    "window": {"sam": "broken window", "en": "Broken window", "es": "Ventana rota", "vi": "Cửa sổ vỡ",
               "zh": "破损窗户", "tl": "Basag na bintana", "ko": "깨진 창문", "ar": "نافذة مكسورة"},
    "tree": {"sam": "fallen tree", "en": "Fallen tree", "es": "Árbol caído", "vi": "Cây đổ", "zh": "倒下的树",
             "tl": "Natumbang puno", "ko": "쓰러진 나무", "ar": "شجرة ساقطة"},
    "roof": {"sam": "damaged roof", "en": "Damaged roof", "es": "Techo dañado", "vi": "Mái nhà hư hại",
             "zh": "受损屋顶", "tl": "Sirang bubong", "ko": "손상된 지붕", "ar": "سقف متضرر"},
    "collapsed": {"sam": "collapsed ceiling", "en": "Fallen ceiling or wall", "es": "Techo o pared caídos",
                  "vi": "Trần hoặc tường bị sập", "zh": "塌落的天花板或墙", "tl": "Gumuhong kisame o pader",
                  "ko": "무너진 천장 또는 벽", "ar": "سقف أو جدار منهار"},
}

# Which concepts the model may ask SAM for, per disaster. "other" may use any.
CONCEPTS_BY_DISASTER = {
    "flood": ["water_line", "standing_water", "mud", "mold", "drywall", "debris", "furniture"],
    "wildfire": ["burned", "soot", "ash", "window", "roof", "debris"],
    "earthquake": ["crack", "collapsed", "debris", "window", "drywall", "furniture"],
    "storm": ["tree", "roof", "window", "debris", "collapsed", "water_line"],
    "heat_outage": ["water_line", "mold", "furniture", "debris"],
    "other": list(CONCEPTS),
}
MAX_CONCEPTS_PER_PHOTO = 3

# --- follow-up questions ------------------------------------------------------------------------
# `hurt` is always asked (code adds it); the model picks up to 3 more from the disaster's list.
OPTIONS = {
    "yes": {"en": "Yes", "es": "Sí", "vi": "Có", "zh": "是", "tl": "Oo", "ko": "예", "ar": "نعم"},
    "no": {"en": "No", "es": "No", "vi": "Không", "zh": "否", "tl": "Hindi", "ko": "아니요", "ar": "لا"},
    "not_sure": {"en": "Not sure", "es": "No estoy seguro", "vi": "Không chắc", "zh": "不确定", "tl": "Hindi sigurado",
                 "ko": "잘 모르겠음", "ar": "لست متأكدًا"},
    "today": {"en": "Today", "es": "Hoy", "vi": "Hôm nay", "zh": "今天", "tl": "Ngayong araw", "ko": "오늘",
              "ar": "اليوم"},
    "days_1_3": {"en": "1 to 3 days ago", "es": "Hace 1 a 3 días", "vi": "1 đến 3 ngày trước", "zh": "1到3天前",
                 "tl": "1 hanggang 3 araw na ang nakalipas", "ko": "1~3일 전", "ar": "قبل 1 إلى 3 أيام"},
    "days_4_7": {"en": "4 to 7 days ago", "es": "Hace 4 a 7 días", "vi": "4 đến 7 ngày trước", "zh": "4到7天前",
                 "tl": "4 hanggang 7 araw na ang nakalipas", "ko": "4~7일 전", "ar": "قبل 4 إلى 7 أيام"},
    "over_week": {"en": "More than a week ago", "es": "Hace más de una semana", "vi": "Hơn một tuần trước",
                  "zh": "一周以前", "tl": "Mahigit isang linggo na", "ko": "일주일 이상 전", "ar": "منذ أكثر من أسبوع"},
    "all_off": {"en": "Yes, all off", "es": "Sí, todo cortado", "vi": "Có, đã tắt hết", "zh": "是，全部关闭",
                "tl": "Oo, lahat ay patay", "ko": "예, 모두 꺼짐", "ar": "نعم، كلها مقطوعة"},
    "some_off": {"en": "Some are off", "es": "Algunos están cortados", "vi": "Một số đã tắt", "zh": "部分关闭",
                 "tl": "Ang ilan ay patay", "ko": "일부만 꺼짐", "ar": "بعضها مقطوع"},
    "none_off": {"en": "No, all still on", "es": "No, todo sigue conectado", "vi": "Không, vẫn còn mở hết",
                 "zh": "否，全部仍开着", "tl": "Hindi, lahat ay bukas pa", "ko": "아니요, 모두 켜져 있음",
                 "ar": "لا، كلها ما زالت تعمل"},
    "own": {"en": "I own it", "es": "Es mía", "vi": "Nhà của tôi", "zh": "自有", "tl": "Akin ito", "ko": "자가",
            "ar": "أملكه"},
    "rent": {"en": "I rent", "es": "La alquilo", "vi": "Tôi thuê", "zh": "租住", "tl": "Umuupa ako", "ko": "임차",
             "ar": "أستأجره"},
    "under_1ft": {"en": "Less than 1 foot (30 cm)", "es": "Menos de 1 pie (30 cm)", "vi": "Dưới 1 foot (30 cm)",
                  "zh": "不到1英尺（30厘米）", "tl": "Mas mababa sa 1 talampakan (30 cm)", "ko": "1피트(30cm) 미만",
                  "ar": "أقل من قدم واحدة (30 سم)"},
    "ft_1_3": {"en": "1 to 3 feet (30 to 90 cm)", "es": "De 1 a 3 pies (30 a 90 cm)", "vi": "1 đến 3 feet (30 đến 90 cm)",
               "zh": "1到3英尺（30到90厘米）", "tl": "1 hanggang 3 talampakan (30 hanggang 90 cm)",
               "ko": "1~3피트(30~90cm)", "ar": "من 1 إلى 3 أقدام (30 إلى 90 سم)"},
    "over_3ft": {"en": "More than 3 feet (90 cm)", "es": "Más de 3 pies (90 cm)", "vi": "Trên 3 feet (90 cm)",
                 "zh": "超过3英尺（90厘米）", "tl": "Higit sa 3 talampakan (90 cm)", "ko": "3피트(90cm) 초과",
                 "ar": "أكثر من 3 أقدام (90 سم)"},
    "under_4h": {"en": "Less than 4 hours", "es": "Menos de 4 horas", "vi": "Dưới 4 giờ", "zh": "不到4小时",
                 "tl": "Mas mababa sa 4 na oras", "ko": "4시간 미만", "ar": "أقل من 4 ساعات"},
    "h_4_24": {"en": "4 to 24 hours", "es": "De 4 a 24 horas", "vi": "4 đến 24 giờ", "zh": "4到24小时",
               "tl": "4 hanggang 24 na oras", "ko": "4~24시간", "ar": "من 4 إلى 24 ساعة"},
    "over_day": {"en": "More than a day", "es": "Más de un día", "vi": "Hơn một ngày", "zh": "超过一天",
                 "tl": "Higit sa isang araw", "ko": "하루 이상", "ar": "أكثر من يوم"},
    "back_on": {"en": "It's back on", "es": "Ya volvió", "vi": "Đã có điện lại", "zh": "已恢复供电",
                "tl": "Bumalik na", "ko": "다시 들어옴", "ar": "عادت الكهرباء"},
}

QUESTIONS = {
    "hurt": {"options": ["yes", "no"],
             "en": "Is anyone hurt?", "es": "¿Hay alguien herido?", "vi": "Có ai bị thương không?",
             "zh": "有人受伤吗？", "tl": "May nasaktan ba?", "ko": "다친 사람이 있나요?", "ar": "هل أصيب أحد؟"},
    "when": {"options": ["today", "days_1_3", "days_4_7", "over_week"],
             "en": "When did the damage happen?", "es": "¿Cuándo ocurrieron los daños?",
             "vi": "Thiệt hại xảy ra khi nào?", "zh": "损坏是什么时候发生的？", "tl": "Kailan nangyari ang pinsala?",
             "ko": "피해는 언제 발생했나요?", "ar": "متى حدث الضرر؟"},
    "gas_smell": {"options": ["yes", "no", "not_sure"],
                  "en": "Do you smell gas or hear hissing?", "es": "¿Huele a gas o escucha un silbido?",
                  "vi": "Bạn có ngửi thấy mùi gas hoặc nghe tiếng xì không?", "zh": "您是否闻到煤气味或听到嘶嘶声？",
                  "tl": "May naaamoy ba kayong gas o naririnig na sumisitsit?", "ko": "가스 냄새가 나거나 쉭 하는 소리가 들리나요?",
                  "ar": "هل تشم رائحة غاز أو تسمع صوت تسرب؟"},
    "utilities": {"options": ["all_off", "some_off", "none_off", "not_sure"],
                  "en": "Are the power, gas and water turned off at the house?",
                  "es": "¿Están cortados la luz, el gas y el agua en la casa?",
                  "vi": "Điện, gas và nước trong nhà đã được tắt chưa?", "zh": "房屋的电、煤气和水都关了吗？",
                  "tl": "Patay na ba ang kuryente, gas at tubig sa bahay?", "ko": "집의 전기, 가스, 수도를 잠갔나요?",
                  "ar": "هل الكهرباء والغاز والماء مقطوعة في المنزل؟"},
    "insurance": {"options": ["yes", "no", "not_sure"],
                  "en": "Do you have home or renters insurance?", "es": "¿Tiene seguro de vivienda o de inquilino?",
                  "vi": "Bạn có bảo hiểm nhà hoặc bảo hiểm cho người thuê nhà không?", "zh": "您有房屋保险或租客保险吗？",
                  "tl": "May insurance ba kayo sa bahay o bilang umuupa?", "ko": "주택 보험이나 세입자 보험이 있나요?",
                  "ar": "هل لديك تأمين على المنزل أو تأمين للمستأجرين؟"},
    "flood_insurance": {"options": ["yes", "no", "not_sure"],
                        "en": "Do you have flood insurance?", "es": "¿Tiene seguro contra inundaciones?",
                        "vi": "Bạn có bảo hiểm lũ lụt không?", "zh": "您有洪水保险吗？", "tl": "May flood insurance ba kayo?",
                        "ko": "홍수 보험이 있나요?", "ar": "هل لديك تأمين ضد الفيضانات؟"},
    "own_rent": {"options": ["own", "rent"],
                 "en": "Do you own or rent your home?", "es": "¿Su casa es propia o alquilada?",
                 "vi": "Nhà bạn là nhà riêng hay nhà thuê?", "zh": "您的住房是自有还是租的？",
                 "tl": "Sa inyo ba ang bahay o inuupahan?", "ko": "집을 소유하고 있나요, 임차하고 있나요?",
                 "ar": "هل تملك منزلك أم تستأجره؟"},
    "water_height": {"options": ["under_1ft", "ft_1_3", "over_3ft", "not_sure"],
                     "en": "How high did the water get inside?", "es": "¿Hasta qué altura llegó el agua adentro?",
                     "vi": "Nước trong nhà ngập cao đến đâu?", "zh": "室内的水最高到多高？",
                     "tl": "Gaano kataas ang tubig sa loob?", "ko": "실내에서 물이 얼마나 높이 찼나요?",
                     "ar": "إلى أي ارتفاع وصل الماء داخل المنزل؟"},
    "stay": {"options": ["yes", "no", "not_sure"],
             "en": "Do you have a place to stay tonight?", "es": "¿Tiene dónde quedarse esta noche?",
             "vi": "Tối nay bạn có chỗ ở không?", "zh": "您今晚有地方住吗？", "tl": "May matutuluyan ba kayo ngayong gabi?",
             "ko": "오늘 밤 머물 곳이 있나요?", "ar": "هل لديك مكان تقيم فيه الليلة؟"},
    "outage": {"options": ["under_4h", "h_4_24", "over_day", "back_on"],
               "en": "How long has the power been out?", "es": "¿Cuánto tiempo lleva sin luz?",
               "vi": "Mất điện bao lâu rồi?", "zh": "停电多久了？", "tl": "Gaano na katagal walang kuryente?",
               "ko": "정전된 지 얼마나 되었나요?", "ar": "منذ متى انقطعت الكهرباء؟"},
}

QUESTIONS_BY_DISASTER = {
    "flood": ["when", "water_height", "flood_insurance", "utilities", "own_rent", "stay"],
    "wildfire": ["when", "insurance", "utilities", "own_rent", "stay"],
    "earthquake": ["gas_smell", "when", "insurance", "own_rent", "stay"],
    "storm": ["when", "insurance", "utilities", "own_rent", "stay"],
    "heat_outage": ["outage", "own_rent", "insurance", "stay"],
    "other": ["when", "insurance", "utilities", "own_rent", "stay"],
}
MAX_EXTRA_QUESTIONS = 3  # plus "hurt": 2 to 4 questions in all

# --- danger: the first line of every screen and of the report -----------------------------------
DANGERS = ("gas", "fire", "water_power", "power_line")

LEAVE_AND_CALL = {
    "en": "Leave the area now and call 911 from a safe place.",
    "es": "Salga del lugar ahora y llame al 911 desde un sitio seguro.",
    "vi": "Hãy rời khỏi khu vực ngay và gọi 911 từ một nơi an toàn.",
    "zh": "请立即离开该区域，到安全的地方拨打 911。",
    "tl": "Umalis na ngayon sa lugar at tumawag sa 911 mula sa ligtas na lugar.",
    "ko": "지금 그 장소를 떠나 안전한 곳에서 911에 전화하세요.",
    "ar": "غادر المكان الآن واتصل بالرقم 911 من مكان آمن.",
}
DANGER_SEEN = {  # "Your photos may show: …" / "You said: …"
    "en": "Your photos or answers may show: {what}.", "es": "Sus fotos o respuestas pueden mostrar: {what}.",
    "vi": "Ảnh hoặc câu trả lời của bạn có thể cho thấy: {what}.", "zh": "您的照片或回答可能显示：{what}。",
    "tl": "Maaaring makita sa inyong mga larawan o sagot: {what}.", "ko": "사진이나 답변에서 다음이 보일 수 있습니다: {what}.",
    "ar": "قد تُظهر صورك أو إجاباتك: {what}.",
}
DANGER_WORDS = {
    "gas": {"en": "a gas leak or damaged gas line", "es": "una fuga de gas o una tubería de gas dañada",
            "vi": "rò rỉ gas hoặc đường ống gas bị hư", "zh": "煤气泄漏或煤气管道受损",
            "tl": "tagas ng gas o sirang linya ng gas", "ko": "가스 누출 또는 손상된 가스관", "ar": "تسرب غاز أو خط غاز متضرر"},
    "fire": {"en": "fire or smoke", "es": "fuego o humo", "vi": "lửa hoặc khói", "zh": "火或烟", "tl": "apoy o usok",
             "ko": "불이나 연기", "ar": "نار أو دخان"},
    "water_power": {"en": "water near outlets, wires or the electrical panel",
                    "es": "agua cerca de enchufes, cables o el panel eléctrico",
                    "vi": "nước gần ổ cắm, dây điện hoặc hộp cầu dao", "zh": "插座、电线或配电箱附近有水",
                    "tl": "tubig malapit sa saksakan, kawad o electrical panel", "ko": "콘센트, 전선 또는 배전반 근처의 물",
                    "ar": "مياه قرب المقابس أو الأسلاك أو لوحة الكهرباء"},
    "power_line": {"en": "a fallen power line", "es": "un cable eléctrico caído", "vi": "dây điện bị đứt rơi xuống",
                   "zh": "掉落的电线", "tl": "bumagsak na linya ng kuryente", "ko": "끊어져 떨어진 전선",
                   "ar": "خط كهرباء ساقط"},
}
HURT_CALL = {
    "en": "If anyone is hurt, call 911 now.", "es": "Si alguien está herido, llame al 911 ahora.",
    "vi": "Nếu có người bị thương, hãy gọi 911 ngay.", "zh": "如果有人受伤，请立即拨打 911。",
    "tl": "Kung may nasaktan, tumawag agad sa 911.", "ko": "다친 사람이 있으면 지금 911에 전화하세요.",
    "ar": "إذا أصيب أحد، اتصل بالرقم 911 الآن.",
}


def danger_lines(dangers: list[str], hurt: bool, lang: str) -> list[str]:
    """The fixed first lines: leave + 911 when danger is seen or reported, 911 when someone is hurt."""
    lines = []
    found = [d for d in DANGERS if d in dangers]
    if found:
        lines.append(LEAVE_AND_CALL[lang])
        lines.append(DANGER_SEEN[lang].format(what=_join([DANGER_WORDS[d][lang] for d in found], lang)))
    if hurt:
        lines.append(HURT_CALL[lang])
    return lines


_AND = {"en": " and ", "es": " y ", "vi": " và ", "zh": "和", "tl": " at ", "ko": ", ", "ar": " و"}


def _join(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    sep = "、" if lang == "zh" else ", "
    return sep.join(items[:-1]) + _AND[lang] + items[-1]


def question_view(qid: str, lang: str) -> dict:
    q = QUESTIONS[qid]
    return {"id": qid, "text": q[lang], "options": [{"id": o, "text": OPTIONS[o][lang]} for o in q["options"]]}


def pick_questions(disaster: str, chosen: list[str]) -> list[str]:
    """"hurt" first, then up to 3 of the model's picks that belong to this disaster (in its order),
    topped up from the disaster's own list so there are always at least 2."""
    allowed = QUESTIONS_BY_DISASTER[disaster]
    extra = [q for q in dict.fromkeys(chosen or []) if q in allowed][:MAX_EXTRA_QUESTIONS]
    if not extra:
        extra = allowed[:2]
    return ["hurt", *extra]
