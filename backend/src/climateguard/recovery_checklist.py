"""What to do next: a fixed checklist for each disaster type, picked in code from the person's answers.

Every item is written here (sources: FEMA/Ready.gov, NFIP, CDC, USDA, EPA, Red Cross). The model never writes
an item; it may only add one short, checked detail sentence to the items marked `detail` ("include the
water line in the living room, photo 1"). EN/ES/VI are written here; zh/tl/ko/ar show the English checklist
with a note, like the supervisor checklist. Phone numbers: FEMA 1-800-621-3362, Red Cross 1-800-733-2767.
"""
REVIEWED = ("en", "es", "vi")

ITEMS = {
    "document": {"detail": True,
        "en": "Document the damage: take photos and video of every room and damaged item before you clean up or throw anything away. Keep this report with them.",
        "es": "Documente los daños: tome fotos y video de cada cuarto y de cada cosa dañada antes de limpiar o tirar algo. Guarde este reporte con ellos.",
        "vi": "Ghi lại thiệt hại: hãy chụp ảnh và quay video từng phòng và từng món đồ bị hư trước khi dọn dẹp hay vứt bỏ bất cứ thứ gì. Giữ bản báo cáo này cùng với chúng."},
    "insurer": {"detail": True,
        "en": "Call your insurance company as soon as you can and ask how to file a claim. Write down the claim number and the name of everyone you talk to.",
        "es": "Llame a su compañía de seguros lo antes posible y pregunte cómo hacer un reclamo. Anote el número de reclamo y el nombre de cada persona con quien hable.",
        "vi": "Hãy gọi cho công ty bảo hiểm càng sớm càng tốt và hỏi cách nộp yêu cầu bồi thường. Ghi lại số hồ sơ và tên của mọi người bạn đã nói chuyện."},
    "flood_policy": {
        "en": "Regular home insurance usually does not cover flooding; flood insurance (NFIP or private) does. With NFIP, send your proof of loss within 60 days.",
        "es": "El seguro de vivienda normal casi nunca cubre inundaciones; el seguro contra inundaciones (NFIP o privado) sí. Con NFIP, envíe su prueba de pérdida (proof of loss) dentro de 60 días.",
        "vi": "Bảo hiểm nhà thông thường thường không chi trả thiệt hại do lũ lụt; bảo hiểm lũ lụt (NFIP hoặc tư nhân) thì có. Với NFIP, hãy gửi giấy chứng minh thiệt hại (proof of loss) trong vòng 60 ngày."},
    "landlord": {"detail": True,
        "en": "Tell your landlord about the damage in writing (text or email) and keep a copy. Renters insurance may cover your belongings.",
        "es": "Avise a su arrendador de los daños por escrito (mensaje de texto o correo) y guarde una copia. El seguro de inquilino puede cubrir sus pertenencias.",
        "vi": "Hãy báo cho chủ nhà về thiệt hại bằng văn bản (tin nhắn hoặc email) và giữ một bản. Bảo hiểm cho người thuê nhà có thể chi trả đồ đạc của bạn."},
    "fema": {"detail": True,
        "en": "If your area has a federal disaster declaration, apply for FEMA assistance at DisasterAssistance.gov or 1-800-621-3362. You can apply even with insurance: FEMA may help with what insurance does not cover.",
        "es": "Si su zona tiene una declaración federal de desastre, solicite ayuda de FEMA en DisasterAssistance.gov o al 1-800-621-3362. Puede solicitarla aunque tenga seguro: FEMA puede ayudar con lo que el seguro no cubre.",
        "vi": "Nếu khu vực của bạn được liên bang công bố thảm họa, hãy xin trợ giúp của FEMA tại DisasterAssistance.gov hoặc số 1-800-621-3362. Bạn vẫn có thể xin dù có bảo hiểm: FEMA có thể giúp phần bảo hiểm không chi trả."},
    "call211": {
        "en": "Call 211 for local help: shelters, food, cleanup crews and repair programs.",
        "es": "Llame al 211 para ayuda local: refugios, comida, equipos de limpieza y programas de reparación.",
        "vi": "Hãy gọi 211 để được giúp đỡ tại địa phương: chỗ trú ẩn, thực phẩm, đội dọn dẹp và chương trình sửa nhà."},
    "shelter": {
        "en": "If you have nowhere to stay tonight, call 211 or the Red Cross at 1-800-733-2767 to find a shelter.",
        "es": "Si no tiene dónde quedarse esta noche, llame al 211 o a la Cruz Roja al 1-800-733-2767 para encontrar un refugio.",
        "vi": "Nếu tối nay bạn không có chỗ ở, hãy gọi 211 hoặc Hội Chữ Thập Đỏ (Red Cross) số 1-800-733-2767 để tìm chỗ trú ẩn."},
    "receipts": {
        "en": "Keep every receipt: hotel, food, cleanup supplies and repairs. Insurance and FEMA may pay some of them back.",
        "es": "Guarde todos los recibos: hotel, comida, artículos de limpieza y reparaciones. El seguro y FEMA pueden devolverle parte.",
        "vi": "Hãy giữ mọi hóa đơn: khách sạn, đồ ăn, đồ dọn dẹp và sửa chữa. Bảo hiểm và FEMA có thể hoàn lại một phần."},
    "gas": {
        "en": "If you smell gas or hear hissing: leave right away, do not use light switches or phones inside, and call 911 or the gas company from outside.",
        "es": "Si huele a gas o escucha un silbido: salga de inmediato, no use interruptores de luz ni teléfonos adentro y llame al 911 o a la compañía de gas desde afuera.",
        "vi": "Nếu ngửi thấy mùi gas hoặc nghe tiếng xì: hãy ra ngoài ngay, không bật công tắc đèn hay dùng điện thoại trong nhà, và gọi 911 hoặc công ty gas từ bên ngoài."},
    "utilities": {
        "en": "Power, gas or water still on: ask your utility company to help turn them off. Never touch switches, outlets or the electrical panel while standing in water.",
        "es": "Si la luz, el gas o el agua siguen conectados: pida ayuda a su compañía de servicios para cortarlos. Nunca toque interruptores, enchufes ni el panel eléctrico si está parado en agua.",
        "vi": "Nếu điện, gas hoặc nước vẫn còn mở: hãy nhờ công ty điện, gas, nước giúp tắt. Tuyệt đối không chạm vào công tắc, ổ cắm hay hộp cầu dao khi đang đứng trong nước."},
    # --- cleanup basics, per disaster ---
    "flood_gear": {
        "en": "Cleanup basics: wear rubber boots, waterproof gloves and an N95 mask around mold. Throw away food that touched floodwater.",
        "es": "Limpieza básica: use botas de hule, guantes impermeables y una mascarilla N95 cerca del moho. Tire la comida que tocó el agua de la inundación.",
        "vi": "Dọn dẹp cơ bản: hãy mang ủng cao su, găng tay chống thấm và khẩu trang N95 khi ở gần nấm mốc. Vứt bỏ thực phẩm đã chạm vào nước lũ."},
    "flood_dry": {
        "en": "Dry the home within 24 to 48 hours if you can: open doors and windows, run fans, and take out wet carpet, drywall and insulation to stop mold.",
        "es": "Seque la casa en 24 a 48 horas si puede: abra puertas y ventanas, use ventiladores y saque alfombras, paneles de pared y aislante mojados para evitar el moho.",
        "vi": "Hãy làm khô nhà trong vòng 24 đến 48 giờ nếu có thể: mở cửa ra vào và cửa sổ, bật quạt, và bỏ thảm, tấm tường và vật liệu cách nhiệt bị ướt để tránh nấm mốc."},
    "flood_power": {
        "en": "Do not turn the power back on or use appliances that got wet until an electrician checks them.",
        "es": "No vuelva a conectar la luz ni use aparatos que se mojaron hasta que un electricista los revise.",
        "vi": "Không bật điện lại hoặc dùng các thiết bị điện đã bị ướt cho đến khi thợ điện kiểm tra."},
    "fire_return": {
        "en": "Go back only when officials say you can. Wear an N95 mask, gloves, long sleeves and sturdy shoes when cleaning ash; mist ash with water before sweeping and never use a leaf blower.",
        "es": "Regrese solo cuando las autoridades lo permitan. Para limpiar ceniza use mascarilla N95, guantes, manga larga y zapatos resistentes; moje la ceniza con un poco de agua antes de barrer y nunca use sopladora de hojas.",
        "vi": "Chỉ quay về khi chính quyền cho phép. Khi dọn tro, hãy đeo khẩu trang N95, găng tay, mặc áo dài tay và mang giày chắc chắn; xịt chút nước lên tro trước khi quét và không bao giờ dùng máy thổi lá."},
    "fire_food": {
        "en": "Throw away food that was exposed to heat, smoke or soot, including canned food that got very hot.",
        "es": "Tire la comida que estuvo expuesta al calor, al humo o al hollín, incluso latas que se calentaron mucho.",
        "vi": "Vứt bỏ thực phẩm đã tiếp xúc với nhiệt, khói hoặc muội than, kể cả đồ hộp đã bị nóng nhiều."},
    "quake_aftershocks": {
        "en": "Expect aftershocks: Drop, Cover and Hold On. Wear sturdy shoes and gloves around broken glass.",
        "es": "Habrá réplicas: Agáchese, Cúbrase y Agárrese. Use zapatos resistentes y guantes cerca de vidrios rotos.",
        "vi": "Sẽ có dư chấn: Cúi xuống, Che chắn và Bám chặt. Hãy mang giày chắc chắn và găng tay khi ở gần kính vỡ."},
    "inspect": {
        "en": "Ask a licensed inspector or your city or county building department to look at cracks in walls, the foundation or the chimney before repairs.",
        "es": "Pida a un inspector con licencia o al departamento de construcción de su ciudad o condado que revise las grietas en paredes, cimientos o chimenea antes de reparar.",
        "vi": "Hãy nhờ thanh tra có giấy phép hoặc sở xây dựng của thành phố hay quận xem các vết nứt ở tường, móng nhà hoặc ống khói trước khi sửa."},
    "storm_lines": {
        "en": "Stay away from fallen power lines and anything touching them, and call the power company.",
        "es": "Aléjese de los cables eléctricos caídos y de todo lo que los toque, y llame a la compañía de luz.",
        "vi": "Tránh xa dây điện bị đứt và mọi thứ đang chạm vào chúng, và gọi công ty điện."},
    "storm_tarp": {
        "en": "Cover holes in the roof or windows with a tarp or plywood to stop more damage, and keep the receipts: insurers expect this.",
        "es": "Cubra los hoyos del techo o las ventanas con una lona o madera para evitar más daños, y guarde los recibos: las aseguradoras lo esperan.",
        "vi": "Hãy che các lỗ thủng trên mái hoặc cửa sổ bằng bạt hoặc ván ép để tránh hư hại thêm, và giữ hóa đơn: công ty bảo hiểm cần điều này."},
    "outage_food": {
        "en": "Food: a fridge keeps food cold about 4 hours and a full freezer about 48 hours if the doors stay closed. Throw away perishable food that was above 40°F for 2 hours or more.",
        "es": "Comida: el refrigerador mantiene la comida fría unas 4 horas y un congelador lleno unas 48 horas si las puertas quedan cerradas. Tire la comida perecedera que estuvo a más de 40°F (4°C) por 2 horas o más.",
        "vi": "Thực phẩm: tủ lạnh giữ lạnh khoảng 4 giờ và ngăn đá đầy khoảng 48 giờ nếu không mở cửa. Vứt bỏ thực phẩm dễ hỏng đã ở trên 40°F (4°C) từ 2 giờ trở lên."},
    "generator": {
        "en": "Use generators and grills only outside, at least 20 feet from doors and windows: their fumes can kill.",
        "es": "Use generadores y parrillas solo afuera, a por lo menos 20 pies (6 metros) de puertas y ventanas: sus gases pueden matar.",
        "vi": "Chỉ dùng máy phát điện và bếp nướng ở ngoài trời, cách cửa ra vào và cửa sổ ít nhất 20 feet (6 mét): khí thải của chúng có thể gây chết người."},
    "cool_place": {
        "en": "If your home is too hot, go to a cooling center or a cool public place: call 211 to find one.",
        "es": "Si su casa está demasiado caliente, vaya a un centro de enfriamiento o a un lugar público fresco: llame al 211 para encontrar uno.",
        "vi": "Nếu nhà quá nóng, hãy đến trung tâm làm mát hoặc nơi công cộng mát mẻ: gọi 211 để tìm."},
    "general_gear": {
        "en": "Cleanup basics: wear sturdy shoes, gloves and long sleeves, and take photos before you throw anything away.",
        "es": "Limpieza básica: use zapatos resistentes, guantes y manga larga, y tome fotos antes de tirar algo.",
        "vi": "Dọn dẹp cơ bản: hãy mang giày chắc chắn, găng tay và mặc áo dài tay, và chụp ảnh trước khi vứt bỏ bất cứ thứ gì."},
}

CLEANUP = {
    "flood": ["flood_power", "flood_dry", "flood_gear"],
    "wildfire": ["fire_return", "fire_food"],
    "earthquake": ["gas", "quake_aftershocks", "inspect"],
    "storm": ["storm_lines", "storm_tarp", "general_gear"],
    "heat_outage": ["outage_food", "generator", "cool_place"],
    "other": ["general_gear"],
}


def pick(disaster: str, answers: dict) -> list[str]:
    """Item ids in order: urgent first, then paperwork, then help, then cleanup basics."""
    a = answers or {}
    ids = []
    if a.get("gas_smell") in ("yes", "not_sure"):
        ids.append("gas")
    if a.get("utilities") in ("some_off", "none_off", "not_sure") and disaster != "heat_outage":
        ids.append("utilities")
    ids.append("document")
    no_insurance = a.get("insurance") == "no" and a.get("flood_insurance") in (None, "no")
    if not no_insurance:
        ids.append("insurer")
    if disaster == "flood":
        ids.append("flood_policy")
    if a.get("own_rent") == "rent":
        ids.append("landlord")
    ids.append("fema")
    if a.get("stay") in ("no", "not_sure"):
        ids.append("shelter")
    ids += ["call211", "receipts"]
    ids += CLEANUP[disaster]
    return list(dict.fromkeys(ids))


def render(ids: list[str], lang: str, details: dict | None = None) -> list[dict]:
    """[{id, text, detail}] in `lang` (English for languages without a written checklist)."""
    use = lang if lang in REVIEWED else "en"
    details = details or {}
    return [{"id": i, "text": ITEMS[i][use], "detail": details.get(i) if ITEMS[i].get("detail") else None}
            for i in ids]
