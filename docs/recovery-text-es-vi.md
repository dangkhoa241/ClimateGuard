# Recovery text for review: Spanish and Vietnamese

Generated from the code (frontend/src/strings.js, recovery_data.py, recovery_checklist.py) on 2026-10-28.

## Spanish

### Screen text
- recIntro: Tome fotos de los daños. ClimateGuard marca los daños que ve, le hace unas preguntas y prepara un reporte para su aseguradora o para quien le ayude.
- recPrivacy: Sus fotos se guardan 24 horas para preparar su reporte y luego se borran. Antes de subir cada foto se quitan la ubicación (GPS) y otros datos ocultos.
- recNotEstimate: No es una estimación oficial de daños.
- recDisasterLabel: ¿Qué pasó?
- recAuto: No estoy seguro: decidir según mis fotos
- recPhotosLabel: Fotos (de 1 a 6)
- recAddPhotos: Agregar fotos
- recAddMore: Agregar más fotos
- recRemovePhoto: Quitar la foto {n}
- recPhotoCount: {n} de 6 fotos
- recCheck: Revisar mis fotos
- recStepPrepare: Preparando las fotos…
- recStepUpload: Subiendo la foto {n} de {total}…
- recStepLook: Revisando sus fotos…
- recStepOutline: Marcando los daños… Puede tardar hasta un minuto.
- recDisasterSeen: Desastre: {label}
- recInferredNote: Sus fotos también podrían mostrar: {label}
- recPhotoN: Foto {n}
- recShowOutlines: Mostrar marcas
- recHideOutlines: Ocultar marcas
- recNothingOutlined: No se marcaron daños en esta foto.
- recQuestionsTitle: Unas preguntas
- recQuestionsIntro: Sus respuestas se incluyen en el reporte.
- recDeleteNow: Borrar mis fotos ahora
- recDeleted: Sus fotos se borraron.
- recStartOver: Empezar de nuevo
- recDeletesAt: Sus fotos se borrarán automáticamente a las {time}.
- recSkipNote: Puede saltar cualquier pregunta.
- recMakeReport: Hacer mi reporte
- recStepReport: Escribiendo su reporte…
- recReportTitle: Reporte de daños en la vivienda
- recReportDate: Hecho el {date}
- recSummary: Resumen
- recAreas: Daños por área
- recPhotosRef: Fotos: {list}
- recYourAnswers: Sus respuestas
- recNextSteps: Qué hacer ahora
- recAiNote: Escrito por IA a partir de sus fotos y respuestas. Revíselo antes de compartirlo.
- recShowEnglish: Mostrar la copia en inglés
- recPrintButton: Imprimir o guardar como PDF
- recPrintHintDesktop: En una computadora: toque el botón de arriba y elija "Guardar como PDF" como impresora.
- recPrintHintIphone: En iPhone: toque el botón de arriba, luego toque Compartir (el cuadro con una flecha) y elija Guardar en Archivos.
- recFallbackEn: No se pudo escribir el reporte en su idioma, así que se muestra en inglés.
- recDisasters.flood: Inundación
- recDisasters.wildfire: Incendio forestal o humo
- recDisasters.earthquake: Terremoto
- recDisasters.storm: Daños por tormenta o tornado
- recDisasters.heat_outage: Calor o corte de luz
- recDisasters.other: Otro
- errors.photo_unreadable: No se pudo abrir esta foto. Elija otra foto o tome una con la cámara.
- errors.photo_too_large: Esta foto es demasiado grande. Elija otra foto.
- errors.not_jpeg: No se pudo leer esta foto. Elija otra foto.
- errors.too_many_photos: Puede agregar hasta 6 fotos.
- errors.no_photos: Agregue al menos una foto.
- errors.analyze_failed: No pudimos revisar sus fotos. Intente de nuevo.
- errors.over_budget: ClimateGuard está muy ocupado hoy. Intente mañana.
- errors.job_not_found: Este reporte ya venció. Empiece de nuevo.
- errors.report_failed: No pudimos escribir su reporte. Intente de nuevo.
- errors.invalid_answers: Revise sus respuestas e intente de nuevo.
- errors.not_ready: Espere a que terminemos de revisar sus fotos.

### Disaster types
- flood: Inundación
- wildfire: Incendio forestal o humo
- earthquake: Terremoto
- storm: Daños por tormenta o tornado
- heat_outage: Calor o corte de luz
- other: Otro

### Damage labels (outline legend)
- water_line: Marca o mancha de agua
- standing_water: Agua estancada
- mud: Lodo
- mold: Moho
- drywall: Pared abierta hasta la estructura
- debris: Escombros
- furniture: Muebles dañados
- burned: Zona quemada
- soot: Hollín
- ash: Ceniza
- crack: Grieta
- window: Ventana rota
- tree: Árbol caído
- roof: Techo dañado
- collapsed: Techo o pared caídos

### Questions
- hurt: ¿Hay alguien herido?  [Sí / No]
- when: ¿Cuándo ocurrieron los daños?  [Hoy / Hace 1 a 3 días / Hace 4 a 7 días / Hace más de una semana]
- gas_smell: ¿Huele a gas o escucha un silbido?  [Sí / No / No estoy seguro]
- utilities: ¿Están cortados la luz, el gas y el agua en la casa?  [Sí, todo cortado / Algunos están cortados / No, todo sigue conectado / No estoy seguro]
- insurance: ¿Tiene seguro de vivienda o de inquilino?  [Sí / No / No estoy seguro]
- flood_insurance: ¿Tiene seguro contra inundaciones?  [Sí / No / No estoy seguro]
- own_rent: ¿Su casa es propia o alquilada?  [Es mía / La alquilo]
- water_height: ¿Hasta qué altura llegó el agua adentro?  [Menos de 1 pie (30 cm) / De 1 a 3 pies (30 a 90 cm) / Más de 3 pies (90 cm) / No estoy seguro]
- stay: ¿Tiene dónde quedarse esta noche?  [Sí / No / No estoy seguro]
- outage: ¿Cuánto tiempo lleva sin luz?  [Menos de 4 horas / De 4 a 24 horas / Más de un día / Ya volvió]

### Danger lines
- leave: Salga del lugar ahora y llame al 911 desde un sitio seguro.
- seen: Sus fotos o respuestas pueden mostrar: {what}.
- hurt: Si alguien está herido, llame al 911 ahora.
- danger.gas: una fuga de gas o una tubería de gas dañada
- danger.fire: fuego o humo
- danger.water_power: agua cerca de enchufes, cables o el panel eléctrico
- danger.power_line: un cable eléctrico caído

### Checklist
- document: Documente los daños: tome fotos y video de cada cuarto y de cada cosa dañada antes de limpiar o tirar algo. Guarde este reporte con ellos.
- insurer: Llame a su compañía de seguros lo antes posible y pregunte cómo hacer un reclamo. Anote el número de reclamo y el nombre de cada persona con quien hable.
- flood_policy: El seguro de vivienda normal casi nunca cubre inundaciones; el seguro contra inundaciones (NFIP o privado) sí. Con NFIP, envíe su prueba de pérdida (proof of loss) dentro de 60 días.
- landlord: Avise a su arrendador de los daños por escrito (mensaje de texto o correo) y guarde una copia. El seguro de inquilino puede cubrir sus pertenencias.
- fema: Si su zona tiene una declaración federal de desastre, solicite ayuda de FEMA en DisasterAssistance.gov o al 1-800-621-3362. Puede solicitarla aunque tenga seguro: FEMA puede ayudar con lo que el seguro no cubre.
- call211: Llame al 211 para ayuda local: refugios, comida, equipos de limpieza y programas de reparación.
- shelter: Si no tiene dónde quedarse esta noche, llame al 211 o a la Cruz Roja al 1-800-733-2767 para encontrar un refugio.
- receipts: Guarde todos los recibos: hotel, comida, artículos de limpieza y reparaciones. El seguro y FEMA pueden devolverle parte.
- gas: Si huele a gas o escucha un silbido: salga de inmediato, no use interruptores de luz ni teléfonos adentro y llame al 911 o a la compañía de gas desde afuera.
- utilities: Si la luz, el gas o el agua siguen conectados: pida ayuda a su compañía de servicios para cortarlos. Nunca toque interruptores, enchufes ni el panel eléctrico si está parado en agua.
- flood_gear: Limpieza básica: use botas de hule, guantes impermeables y una mascarilla N95 cerca del moho. Tire la comida que tocó el agua de la inundación.
- flood_dry: Seque la casa en 24 a 48 horas si puede: abra puertas y ventanas, use ventiladores y saque alfombras, paneles de pared y aislante mojados para evitar el moho.
- flood_power: No vuelva a conectar la luz ni use aparatos que se mojaron hasta que un electricista los revise.
- fire_return: Regrese solo cuando las autoridades lo permitan. Para limpiar ceniza use mascarilla N95, guantes, manga larga y zapatos resistentes; moje la ceniza con un poco de agua antes de barrer y nunca use sopladora de hojas.
- fire_food: Tire la comida que estuvo expuesta al calor, al humo o al hollín, incluso latas que se calentaron mucho.
- quake_aftershocks: Habrá réplicas: Agáchese, Cúbrase y Agárrese. Use zapatos resistentes y guantes cerca de vidrios rotos.
- inspect: Pida a un inspector con licencia o al departamento de construcción de su ciudad o condado que revise las grietas en paredes, cimientos o chimenea antes de reparar.
- storm_lines: Aléjese de los cables eléctricos caídos y de todo lo que los toque, y llame a la compañía de luz.
- tarp: Cubra los hoyos del techo o las ventanas con una lona o madera para evitar más daños, pero solo si es seguro y desde el suelo; nunca se suba a un techo dañado. Si no puede hacerlo sin peligro, no lo haga y tome fotos de los daños. Guarde los recibos.
- outage_food: Comida: el refrigerador mantiene la comida fría unas 4 horas y un congelador lleno unas 48 horas si las puertas quedan cerradas. Tire la comida perecedera que estuvo a más de 40°F (4°C) por 2 horas o más.
- generator: Use generadores y parrillas solo afuera, a por lo menos 20 pies (6 metros) de puertas y ventanas: sus gases pueden matar.
- cool_place: Si su casa está demasiado caliente, vaya a un centro de enfriamiento o a un lugar público fresco: llame al 211 para encontrar uno.
- general_gear: Limpieza básica: use zapatos resistentes, guantes y manga larga, y tome fotos antes de tirar algo.

## Vietnamese

### Screen text
- recIntro: Hãy chụp ảnh chỗ bị thiệt hại. ClimateGuard sẽ khoanh vùng thiệt hại nhìn thấy được, hỏi bạn vài câu và làm một bản báo cáo để bạn gửi cho công ty bảo hiểm hoặc người giúp đỡ.
- recPrivacy: Ảnh của bạn được giữ 24 giờ để làm báo cáo, sau đó sẽ bị xóa. Vị trí (GPS) và các dữ liệu ẩn khác được xóa khỏi từng ảnh trước khi tải lên.
- recNotEstimate: Không phải bản ước tính thiệt hại chính thức.
- recDisasterLabel: Chuyện gì đã xảy ra?
- recAuto: Không chắc: hãy dựa vào ảnh của tôi
- recPhotosLabel: Ảnh (từ 1 đến 6)
- recAddPhotos: Thêm ảnh
- recAddMore: Thêm ảnh khác
- recRemovePhoto: Bỏ ảnh {n}
- recPhotoCount: {n} trên 6 ảnh
- recCheck: Kiểm tra ảnh của tôi
- recStepPrepare: Đang chuẩn bị ảnh…
- recStepUpload: Đang tải ảnh {n} trên {total}…
- recStepLook: Đang xem ảnh của bạn…
- recStepOutline: Đang khoanh vùng thiệt hại… Có thể mất đến một phút.
- recDisasterSeen: Thiên tai: {label}
- recInferredNote: Ảnh của bạn cũng có thể cho thấy: {label}
- recPhotoN: Ảnh {n}
- recShowOutlines: Hiện vùng khoanh
- recHideOutlines: Ẩn vùng khoanh
- recNothingOutlined: Không khoanh được thiệt hại nào trong ảnh này.
- recQuestionsTitle: Vài câu hỏi
- recQuestionsIntro: Câu trả lời của bạn sẽ được đưa vào báo cáo.
- recDeleteNow: Xóa ảnh của tôi ngay
- recDeleted: Ảnh của bạn đã được xóa.
- recStartOver: Làm lại từ đầu
- recDeletesAt: Ảnh của bạn sẽ tự động bị xóa lúc {time}.
- recSkipNote: Bạn có thể bỏ qua bất kỳ câu hỏi nào.
- recMakeReport: Làm báo cáo của tôi
- recStepReport: Đang viết báo cáo…
- recReportTitle: Báo cáo thiệt hại nhà
- recReportDate: Lập ngày {date}
- recSummary: Tóm tắt
- recAreas: Thiệt hại theo từng khu vực
- recPhotosRef: Ảnh: {list}
- recYourAnswers: Câu trả lời của bạn
- recNextSteps: Việc cần làm tiếp theo
- recAiNote: Do AI viết dựa trên ảnh và câu trả lời của bạn. Hãy đọc lại trước khi chia sẻ.
- recShowEnglish: Xem bản tiếng Anh
- recPrintButton: In hoặc lưu thành PDF
- recPrintHintDesktop: Trên máy tính: bấm nút ở trên và chọn "Lưu dưới dạng PDF" (Save as PDF) làm máy in.
- recPrintHintIphone: Trên iPhone: bấm nút ở trên, sau đó bấm Chia sẻ (hình vuông có mũi tên) và chọn Lưu vào Tệp.
- recFallbackEn: Không viết được báo cáo bằng ngôn ngữ của bạn, nên báo cáo được hiển thị bằng tiếng Anh.
- recDisasters.flood: Lũ lụt
- recDisasters.wildfire: Cháy rừng hoặc khói
- recDisasters.earthquake: Động đất
- recDisasters.storm: Thiệt hại do bão hoặc lốc xoáy
- recDisasters.heat_outage: Nắng nóng hoặc mất điện
- recDisasters.other: Khác
- errors.photo_unreadable: Không mở được ảnh này. Hãy chọn ảnh khác hoặc chụp bằng máy ảnh.
- errors.photo_too_large: Ảnh này quá lớn. Hãy chọn ảnh khác.
- errors.not_jpeg: Không đọc được ảnh này. Hãy chọn ảnh khác.
- errors.too_many_photos: Bạn có thể thêm tối đa 6 ảnh.
- errors.no_photos: Hãy thêm ít nhất một ảnh.
- errors.analyze_failed: Chưa kiểm tra được ảnh của bạn. Hãy thử lại.
- errors.over_budget: Hôm nay ClimateGuard đang rất bận. Hãy thử lại vào ngày mai.
- errors.job_not_found: Báo cáo này đã hết hạn. Hãy làm lại từ đầu.
- errors.report_failed: Chưa viết được báo cáo. Hãy thử lại.
- errors.invalid_answers: Hãy kiểm tra lại câu trả lời rồi thử lại.
- errors.not_ready: Hãy đợi kiểm tra xong ảnh của bạn.

### Disaster types
- flood: Lũ lụt
- wildfire: Cháy rừng hoặc khói
- earthquake: Động đất
- storm: Thiệt hại do bão hoặc lốc xoáy
- heat_outage: Nắng nóng hoặc mất điện
- other: Khác

### Damage labels (outline legend)
- water_line: Vệt nước
- standing_water: Nước đọng
- mud: Bùn
- mold: Nấm mốc
- drywall: Tường bị lột trơ khung
- debris: Mảnh vụn
- furniture: Đồ đạc hư hại
- burned: Chỗ bị cháy
- soot: Muội than
- ash: Tro
- crack: Vết nứt
- window: Cửa sổ vỡ
- tree: Cây đổ
- roof: Mái nhà hư hại
- collapsed: Trần hoặc tường bị sập

### Questions
- hurt: Có ai bị thương không?  [Có / Không]
- when: Thiệt hại xảy ra khi nào?  [Hôm nay / 1 đến 3 ngày trước / 4 đến 7 ngày trước / Hơn một tuần trước]
- gas_smell: Bạn có ngửi thấy mùi gas hoặc nghe tiếng xì không?  [Có / Không / Không chắc]
- utilities: Điện, gas và nước trong nhà đã được tắt chưa?  [Có, đã tắt hết / Một số đã tắt / Không, vẫn còn mở hết / Không chắc]
- insurance: Bạn có bảo hiểm nhà hoặc bảo hiểm cho người thuê nhà không?  [Có / Không / Không chắc]
- flood_insurance: Bạn có bảo hiểm lũ lụt không?  [Có / Không / Không chắc]
- own_rent: Nhà bạn là nhà riêng hay nhà thuê?  [Nhà của tôi / Tôi thuê]
- water_height: Nước trong nhà ngập cao đến đâu?  [Dưới 1 foot (30 cm) / 1 đến 3 feet (30 đến 90 cm) / Trên 3 feet (90 cm) / Không chắc]
- stay: Tối nay bạn có chỗ ở không?  [Có / Không / Không chắc]
- outage: Mất điện bao lâu rồi?  [Dưới 4 giờ / 4 đến 24 giờ / Hơn một ngày / Đã có điện lại]

### Danger lines
- leave: Hãy rời khỏi khu vực ngay và gọi 911 từ một nơi an toàn.
- seen: Ảnh hoặc câu trả lời của bạn có thể cho thấy: {what}.
- hurt: Nếu có người bị thương, hãy gọi 911 ngay.
- danger.gas: rò rỉ gas hoặc đường ống gas bị hư
- danger.fire: lửa hoặc khói
- danger.water_power: nước gần ổ cắm, dây điện hoặc hộp cầu dao
- danger.power_line: dây điện bị đứt rơi xuống

### Checklist
- document: Ghi lại thiệt hại: hãy chụp ảnh và quay video từng phòng và từng món đồ bị hư trước khi dọn dẹp hay vứt bỏ bất cứ thứ gì. Giữ bản báo cáo này cùng với chúng.
- insurer: Hãy gọi cho công ty bảo hiểm càng sớm càng tốt và hỏi cách nộp yêu cầu bồi thường. Ghi lại số hồ sơ và tên của mọi người bạn đã nói chuyện.
- flood_policy: Bảo hiểm nhà thông thường thường không chi trả thiệt hại do lũ lụt; bảo hiểm lũ lụt (NFIP hoặc tư nhân) thì có. Với NFIP, hãy gửi giấy chứng minh thiệt hại (proof of loss) trong vòng 60 ngày.
- landlord: Hãy báo cho chủ nhà về thiệt hại bằng văn bản (tin nhắn hoặc email) và giữ một bản. Bảo hiểm cho người thuê nhà có thể chi trả đồ đạc của bạn.
- fema: Nếu khu vực của bạn được liên bang công bố thảm họa, hãy xin trợ giúp của FEMA tại DisasterAssistance.gov hoặc số 1-800-621-3362. Bạn vẫn có thể xin dù có bảo hiểm: FEMA có thể giúp phần bảo hiểm không chi trả.
- call211: Hãy gọi 211 để được giúp đỡ tại địa phương: chỗ trú ẩn, thực phẩm, đội dọn dẹp và chương trình sửa nhà.
- shelter: Nếu tối nay bạn không có chỗ ở, hãy gọi 211 hoặc Hội Chữ Thập Đỏ (Red Cross) số 1-800-733-2767 để tìm chỗ trú ẩn.
- receipts: Hãy giữ mọi hóa đơn: khách sạn, đồ ăn, đồ dọn dẹp và sửa chữa. Bảo hiểm và FEMA có thể hoàn lại một phần.
- gas: Nếu ngửi thấy mùi gas hoặc nghe tiếng xì: hãy ra ngoài ngay, không bật công tắc đèn hay dùng điện thoại trong nhà, và gọi 911 hoặc công ty gas từ bên ngoài.
- utilities: Nếu điện, gas hoặc nước vẫn còn mở: hãy nhờ công ty điện, gas, nước giúp tắt. Tuyệt đối không chạm vào công tắc, ổ cắm hay hộp cầu dao khi đang đứng trong nước.
- flood_gear: Dọn dẹp cơ bản: hãy mang ủng cao su, găng tay chống thấm và khẩu trang N95 khi ở gần nấm mốc. Vứt bỏ thực phẩm đã chạm vào nước lũ.
- flood_dry: Hãy làm khô nhà trong vòng 24 đến 48 giờ nếu có thể: mở cửa ra vào và cửa sổ, bật quạt, và bỏ thảm, tấm tường và vật liệu cách nhiệt bị ướt để tránh nấm mốc.
- flood_power: Không bật điện lại hoặc dùng các thiết bị điện đã bị ướt cho đến khi thợ điện kiểm tra.
- fire_return: Chỉ quay về khi chính quyền cho phép. Khi dọn tro, hãy đeo khẩu trang N95, găng tay, mặc áo dài tay và mang giày chắc chắn; xịt chút nước lên tro trước khi quét và không bao giờ dùng máy thổi lá.
- fire_food: Vứt bỏ thực phẩm đã tiếp xúc với nhiệt, khói hoặc muội than, kể cả đồ hộp đã bị nóng nhiều.
- quake_aftershocks: Sẽ có dư chấn: Cúi xuống, Che chắn và Bám chặt. Hãy mang giày chắc chắn và găng tay khi ở gần kính vỡ.
- inspect: Hãy nhờ thanh tra có giấy phép hoặc sở xây dựng của thành phố hay quận xem các vết nứt ở tường, móng nhà hoặc ống khói trước khi sửa.
- storm_lines: Tránh xa dây điện bị đứt và mọi thứ đang chạm vào chúng, và gọi công ty điện.
- tarp: Hãy che các lỗ thủng trên mái hoặc cửa sổ bằng bạt hoặc ván ép để tránh hư hại thêm, nhưng chỉ khi an toàn và làm từ dưới đất; tuyệt đối không trèo lên mái nhà bị hư. Nếu không làm được một cách an toàn, hãy bỏ qua và chụp ảnh thiệt hại. Giữ lại hóa đơn.
- outage_food: Thực phẩm: tủ lạnh giữ lạnh khoảng 4 giờ và ngăn đá đầy khoảng 48 giờ nếu không mở cửa. Vứt bỏ thực phẩm dễ hỏng đã ở trên 40°F (4°C) từ 2 giờ trở lên.
- generator: Chỉ dùng máy phát điện và bếp nướng ở ngoài trời, cách cửa ra vào và cửa sổ ít nhất 20 feet (6 mét): khí thải của chúng có thể gây chết người.
- cool_place: Nếu nhà quá nóng, hãy đến trung tâm làm mát hoặc nơi công cộng mát mẻ: gọi 211 để tìm.
- general_gear: Dọn dẹp cơ bản: hãy mang giày chắc chắn, găng tay và mặc áo dài tay, và chụp ảnh trước khi vứt bỏ bất cứ thứ gì.

