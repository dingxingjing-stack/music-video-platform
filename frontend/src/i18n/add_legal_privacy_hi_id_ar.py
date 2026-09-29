"""一次性注入脚本：为 hi / id / ar 补齐 legal.privacy 命名空间（41 条真译文）。

背景
----
其余 8 个语种（zh/ja/ko/de/fr/es/pt/ru）均已译全 legal.privacy（41/42，仅
contactEmail 为邮箱不译）。hi/id/ar 此前只译了 links + 标题 + updated/effective/
version/rights（15 条），legal.privacy 整段缺失 —— 运行时经 useTranslation 的
「当前语言 → 英文 → key」回退链会显示英文正文，与其它语种不一致。

口径
----
- 键序严格对齐 en.json 的 legal.privacy 键序（便于 diff 与后续 parity 比对）
- 模型名/厂商名保留拉丁原名（Yinchao / TemPolor / Agnes AI / NVIDIA / Google
  Gemini 及型号字符串），与 zh/ja 的既有译法一致，不做意译
- contactEmail 是邮箱，原样保留（因此 hi/id/ar 会显示 41 译为 42 中；与 zh 相同）
- 幂等：重复执行结果一致；已存在同值则不报错

用法
----
    python frontend/src/i18n/add_legal_privacy_hi_id_ar.py          # 写入
    python frontend/src/i18n/add_legal_privacy_hi_id_ar.py --check  # 只校验不写入
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCALES = Path(__file__).resolve().parent / "locales"
LANGS = ("hi", "id", "ar")

# 邮箱：不翻译，与 en 及全部既有语种保持一致
_CONTACT_EMAIL = "zezhending@gmail.com"

HI: dict[str, str] = {
    "sec1Title": "परिचय",
    "sec1Body": "यह गोपनीयता नीति बताती है कि जब आप हमारी AI संगीत निर्माण सेवा का उपयोग करते हैं तो Melovar आपके डेटा को कैसे एकत्र, उपयोग, संग्रहीत और सुरक्षित करता है। प्लेटफ़ॉर्म तक पहुँचने या उसका उपयोग करने से आप पुष्टि करते हैं कि आपने इस नीति को पढ़ और समझ लिया है।",
    "sec2Title": "हम कौन-सी जानकारी एकत्र करते हैं",
    "sec2Lead": "हम केवल वही एकत्र करते हैं जो सेवा चलाने के लिए आवश्यक है, और तभी जब आप उसे प्रदान करते हैं या वह आपके उपयोग से उत्पन्न होता है:",
    "sec2i1": "खाता जानकारी – वह ईमेल पता जिससे आप पंजीकरण करते हैं, एक वैकल्पिक उपयोगकर्ता नाम, और आयु का मान, जिसका उपयोग केवल न्यूनतम आयु की आवश्यकता लागू करने के लिए किया जाता है।",
    "sec2i2": "निर्माण सामग्री – आपके द्वारा भेजे गए प्रॉम्प्ट, गीत के बोल और प्रोजेक्ट डेटा, तथा उनसे उत्पन्न ऑडियो फ़ाइलें।",
    "sec2i3": "तकनीकी और लॉग डेटा – डिवाइस तथा ब्राउज़र की जानकारी, IP पता और उपयोग लॉग, जिनका उपयोग समस्या निवारण, सुरक्षा और सेवा सुधार के लिए किया जाता है।",
    "sec2i4": "ऑर्डर और लेन-देन डेटा – आपके द्वारा खरीदी गई वस्तु देने के लिए आवश्यक न्यूनतम जानकारी: ऑर्डर/लेन-देन आईडी, लेन-देन की स्थिति, मुद्रा और राशि, तथा खरीदा गया क्रेडिट्स पैक या प्लान। इसमें भुगतान कार्ड की जानकारी कभी शामिल नहीं होती।",
    "sec2negLead": "हम यह एकत्र नहीं करते:",
    "sec2neg1": "पूर्ण भुगतान कार्ड नंबर, CVV/CVC कोड या बैंक खाते की जानकारी – भुगतान हमारे तृतीय-पक्ष प्रदाता Paddle द्वारा Merchant of Record के रूप में संभाला जाता है, जो यह जानकारी सीधे एकत्र और संसाधित करता है; Melovar इसे न तो एकत्र करता है और न ही संग्रहीत करता है।",
    "sec3Title": "हम आपके डेटा का उपयोग कैसे करते हैं",
    "sec3Lead": "आपके डेटा का उपयोग केवल निम्नलिखित उद्देश्यों के लिए किया जाता है:",
    "sec3i1": "सेवा प्रदान करना, बनाए रखना और उसमें सुधार करना।",
    "sec3i2": "आपके द्वारा अनुरोधित संगीत निर्माण और ऑडियो टूल चलाना।",
    "sec3i3": "उपयोग की सीमाएँ लागू करना तथा दुरुपयोग, धोखाधड़ी और तकनीकी विफलताओं को रोकना।",
    "sec3i4": "त्रुटियों का निदान करना, सुरक्षा की रक्षा करना और कानूनी दायित्वों का पालन करना।",
    "sec3i5": "आपके द्वारा खरीदे गए क्रेडिट्स और सदस्यता लाभ प्रदान करना, तथा मिलान, ग्राहक सहायता और विवाद निपटान के लिए।",
    "sec4Title": "भंडारण और प्रतिधारण",
    "sec4Body": "खाता और प्रोजेक्ट रिकॉर्ड हमारे द्वारा प्रबंधित PostgreSQL डेटाबेस में संग्रहीत होते हैं; ऑडियो फ़ाइलें एक निजी ऑब्जेक्ट-स्टोरेज बकेट में रखी जाती हैं; हमारे द्वारा जारी प्लेबैक लिंक अल्पकालिक हस्ताक्षरित URL होते हैं जो स्वतः समाप्त हो जाते हैं। उपयोग काउंटर प्रतिदिन और प्रतिमाह रीसेट होते हैं।",
    "sec4i1": "जब आप My Creations में कोई कार्य या रचना हटाते हैं, तो उसकी ऑडियो फ़ाइलें और संबंधित रिकॉर्ड भी हटा दिए जाते हैं।",
    "sec4i2": "जिन डेटा की आवश्यकता नहीं रहती, उन्हें हटा दिया जाता है या अनाम कर दिया जाता है, और हम विलोपन अनुरोधों को लागू कानून की सीमाओं के भीतर संभालते हैं।",
    "sec4i3": "हमारा त्रुटि-निगरानी प्रदाता सीमित अवधि के लिए नैदानिक डेटा बनाए रख सकता है।",
    "sec5Title": "साझाकरण और तृतीय पक्ष",
    "sec5Lead": "हम आपका व्यक्तिगत डेटा नहीं बेचते। सेवा देने के लिए हमें आवश्यक डेटा इन्हें देना होता है:",
    "sec5i1": "AI संगीत निर्माण और संबंधित सुविधाएँ प्रदान करने के लिए, हम किसी सुविधा को संसाधित करने हेतु आवश्यक उपयोगकर्ता इनपुट — सामान्यतः प्रॉम्प्ट और गीत के बोल, तथा जहाँ सुविधा के लिए आवश्यक हो वहाँ ऑडियो — तृतीय-पक्ष AI सेवा प्रदाताओं को भेज सकते हैं। ऑडियो उत्पन्न करने वाली सेवाएँ तृतीय-पक्ष AI संगीत निर्माण सेवाएँ हैं, वर्तमान में Yinchao v4.0 और TemPolor tempolor-latest। पाठ सहायता — प्रॉम्प्ट अनुकूलन और गीत-संबंधी प्रसंस्करण — के लिए वर्तमान में Agnes AI agnes-2.0-flash और Google Gemini gemini-2.0-flash का उपयोग किया जाता है, तथा NVIDIA पाठ-प्रसंस्करण की सहायक क्षमता के रूप में उपलब्ध है; ये सभी टेक्स्ट मॉडल हैं और अंतिम संगीत ऑडियो उत्पन्न नहीं करते। वास्तव में कौन-सा प्रदाता उपयोग होगा यह सुविधा, उसकी उपलब्धता और हमारे सिस्टम कॉन्फ़िगरेशन पर निर्भर करता है, और प्रत्येक को उसके कार्य के लिए आवश्यक इनपुट मिलता है। ऊपर दिए गए मॉडल नाम हमारे द्वारा कॉल की जाने वाली सेवाओं की पहचान के लिए हैं, और प्रत्येक प्रदाता अपने मॉडल, प्रशिक्षण डेटा और अधोसंरचना का स्वयं प्रबंधन करता है। तृतीय-पक्ष AI सेवा प्रदाता और उनके द्वारा दिए जाने वाले मॉडल संस्करण हमारी उत्पाद सुविधाओं, तकनीकी आवश्यकताओं या सेवा उपलब्धता के विकास के साथ बदल सकते हैं; महत्वपूर्ण परिवर्तनों की सूचना इस नीति के अद्यतन तथा लागू कानून द्वारा अपेक्षित किसी अन्य माध्यम से दी जाएगी।",
    "sec5i2": "अधोसंरचना, होस्टिंग, भंडारण और त्रुटि-निगरानी प्रदाता जो हमारी ओर से प्लेटफ़ॉर्म चलाते हैं।",
    "sec5i3": "अधिकारी, जहाँ कानून या वैध कानूनी अनुरोध द्वारा आवश्यक हो; अथवा विलय या परिसंपत्ति हस्तांतरण की स्थिति में उत्तराधिकारी, जो इस नीति से बाध्य रहेगा।",
    "sec5i4": "हमारा भुगतान प्रदाता Paddle, जो भुगतान, रसीदों और चालानों, धनवापसी तथा संबंधित करों के लिए Merchant of Record के रूप में कार्य करता है और आपकी भुगतान जानकारी सीधे एकत्र करता है।",
    "sec6Title": "आपके अधिकार",
    "sec6Lead": "लागू डेटा संरक्षण कानून के अधीन, आप यह कर सकते हैं:",
    "sec6i1": "आपके बारे में हमारे पास मौजूद डेटा तक पहुँचना और उसकी प्रति प्राप्त करना।",
    "sec6i2": "गलत डेटा को ठीक करवाना, तथा जहाँ कानून अनुमति दे वहाँ अपना डेटा या रचनाएँ हटवाना।",
    "sec6i3": "प्रसंस्करण के लिए दी गई सहमति वापस लेना, अथवा किसी विशेष प्रसंस्करण पर आपत्ति करना या उसे सीमित करवाना।",
    "sec6i4": "अपने स्थानीय डेटा संरक्षण प्राधिकरण के पास शिकायत दर्ज करना।",
    "sec7Title": "सुरक्षा",
    "sec7Body": "ऐप और हमारे सर्वरों के बीच यातायात ट्रांज़िट में एन्क्रिप्टेड रहता है, और प्रत्येक कार्य, डाउनलोड लिंक तथा रचना आपके साइन-इन किए गए खाते के विरुद्ध जाँची जाती है ताकि अन्य उसे न पढ़ सकें। कुंजियाँ केवल सर्वर-साइड, न्यूनतम विशेषाधिकार के अंतर्गत रखी जाती हैं। संचरण या भंडारण की कोई भी विधि पूर्णतः सुरक्षित होने की गारंटी नहीं दे सकती।",
    "sec8Title": "इस नीति में परिवर्तन",
    "sec8Body": "हम समय-समय पर इस गोपनीयता नीति को अद्यतन कर सकते हैं। वर्तमान संस्करण सदैव इस पृष्ठ पर प्रकाशित रहता है, और महत्वपूर्ण परिवर्तनों की घोषणा लागू होने से पहले उत्पाद में या किसी अन्य उपयुक्त माध्यम से की जाएगी।",
    "sec9Title": "हमसे संपर्क करें",
    "sec9Body": "यदि इस गोपनीयता नीति या अपने व्यक्तिगत डेटा के संबंध में आपका कोई प्रश्न, अनुरोध या शिकायत है, तो आप हमसे ईमेल द्वारा संपर्क कर सकते हैं:",
    "footerNote": "किसी अद्यतन के बाद Melovar का उपयोग जारी रखने का अर्थ है कि आप इस गोपनीयता नीति के वर्तमान संस्करण को स्वीकार करते हैं।",
}

ID: dict[str, str] = {
    "sec1Title": "Pendahuluan",
    "sec1Body": "Kebijakan Privasi ini menjelaskan bagaimana Melovar mengumpulkan, menggunakan, menyimpan, dan melindungi data Anda saat Anda menggunakan layanan pembuatan musik AI kami. Dengan mengakses atau menggunakan platform ini, Anda menyatakan telah membaca dan memahami kebijakan ini.",
    "sec2Title": "Informasi yang kami kumpulkan",
    "sec2Lead": "Kami hanya mengumpulkan data yang diperlukan untuk menjalankan layanan, dan hanya ketika Anda memberikannya atau data itu timbul dari penggunaan Anda:",
    "sec2i1": "Informasi akun – alamat email yang Anda gunakan untuk mendaftar, nama pengguna (opsional), dan nilai usia, yang semata-mata digunakan untuk menegakkan persyaratan usia minimum.",
    "sec2i2": "Konten kreasi – prompt, lirik, dan data proyek yang Anda kirimkan, serta berkas audio yang dihasilkan darinya.",
    "sec2i3": "Data teknis dan log – informasi perangkat dan peramban, alamat IP, serta log penggunaan, yang digunakan untuk penelusuran masalah, keamanan, dan peningkatan layanan.",
    "sec2i4": "Data pesanan dan transaksi – data minimum yang diperlukan untuk menyerahkan apa yang Anda beli: ID pesanan/transaksi, status transaksi, mata uang dan jumlah, serta paket atau langganan Kredit yang dibeli. Data ini tidak pernah mencakup kredensial kartu pembayaran.",
    "sec2negLead": "Kami tidak mengumpulkan:",
    "sec2neg1": "Nomor kartu pembayaran lengkap, kode CVV/CVC, atau kredensial rekening bank – pembayaran ditangani oleh penyedia pihak ketiga kami, Paddle, yang bertindak sebagai Merchant of Record dan mengumpulkan serta memproses kredensial tersebut secara langsung; Melovar tidak mengumpulkan maupun menyimpannya.",
    "sec3Title": "Cara kami menggunakan data Anda",
    "sec3Lead": "Data Anda hanya digunakan untuk tujuan berikut:",
    "sec3i1": "Menyediakan, memelihara, dan meningkatkan layanan.",
    "sec3i2": "Menjalankan pembuatan musik dan perkakas audio yang Anda minta.",
    "sec3i3": "Menegakkan batas penggunaan serta mencegah penyalahgunaan, penipuan, dan kegagalan teknis.",
    "sec3i4": "Mendiagnosis kesalahan, melindungi keamanan, dan mematuhi kewajiban hukum.",
    "sec3i5": "Memberikan Kredit dan manfaat langganan yang Anda beli, serta untuk rekonsiliasi, dukungan pelanggan, dan penanganan sengketa.",
    "sec4Title": "Penyimpanan dan retensi",
    "sec4Body": "Catatan akun dan proyek disimpan dalam basis data PostgreSQL yang kami kelola; berkas audio disimpan dalam bucket penyimpanan objek privat; tautan pemutaran yang kami berikan berupa URL bertanda tangan berumur pendek yang kedaluwarsa secara otomatis. Penghitung penggunaan direset setiap hari dan setiap bulan.",
    "sec4i1": "Saat Anda menghapus tugas atau karya di My Creations, berkas audio dan catatan terkaitnya juga dihapus.",
    "sec4i2": "Data yang tidak lagi diperlukan akan dihapus atau dianonimkan, dan kami menangani permintaan penghapusan dalam batas hukum yang berlaku.",
    "sec4i3": "Penyedia pemantauan kesalahan kami dapat menyimpan data diagnostik untuk jangka waktu terbatas.",
    "sec5Title": "Berbagi data dan pihak ketiga",
    "sec5Lead": "Kami tidak menjual data pribadi Anda. Untuk menyediakan layanan, kami harus meneruskan data yang diperlukan kepada:",
    "sec5i1": "Untuk menyediakan pembuatan musik AI dan fitur terkait, kami dapat meneruskan masukan pengguna yang perlu diproses oleh fitur tertentu — umumnya prompt dan lirik, serta audio bila fitur memerlukannya — kepada penyedia layanan AI pihak ketiga. Penyedia yang menghasilkan audio adalah layanan pembuatan musik AI pihak ketiga, saat ini Yinchao v4.0 dan TemPolor tempolor-latest. Penyedia untuk bantuan teks — optimalisasi prompt dan pemrosesan terkait lirik — adalah Agnes AI agnes-2.0-flash dan Google Gemini gemini-2.0-flash, dengan NVIDIA tersedia sebagai kapasitas pemrosesan teks tambahan; semuanya adalah model teks dan tidak menghasilkan audio musik akhir. Penyedia yang benar-benar digunakan bergantung pada fitur, ketersediaannya, dan konfigurasi sistem kami, dan masing-masing menerima masukan yang diperlukan untuk fungsi yang dijalankannya. Sebutan model di atas berfungsi mengidentifikasi layanan yang kami panggil, dan setiap penyedia mengelola model, data pelatihan, serta infrastrukturnya sendiri. Penyedia layanan AI pihak ketiga dan versi model yang mereka tawarkan dapat berubah seiring perkembangan fitur produk, kebutuhan teknis, atau ketersediaan layanan; perubahan material akan disampaikan melalui pembaruan kebijakan ini dan pemberitahuan lain yang diwajibkan hukum yang berlaku.",
    "sec5i2": "Penyedia infrastruktur, hosting, penyimpanan, dan pemantauan kesalahan yang mengoperasikan platform atas nama kami.",
    "sec5i3": "Otoritas, bila diwajibkan hukum atau permintaan hukum yang sah; atau penerus dalam penggabungan usaha atau pengalihan aset, yang tetap terikat pada kebijakan ini.",
    "sec5i4": "Penyedia pembayaran kami, Paddle, yang bertindak sebagai Merchant of Record untuk pembayaran, kuitansi dan faktur, pengembalian dana, serta pajak terkait, dan yang mengumpulkan kredensial pembayaran Anda secara langsung.",
    "sec6Title": "Hak Anda",
    "sec6Lead": "Dengan tunduk pada hukum perlindungan data yang berlaku, Anda dapat:",
    "sec6i1": "Mengakses data yang kami simpan tentang Anda dan memperoleh salinannya.",
    "sec6i2": "Meminta perbaikan data yang tidak akurat, serta penghapusan data atau karya Anda sejauh diizinkan hukum.",
    "sec6i3": "Menarik persetujuan atas pemrosesan, atau menolak atau membatasi pemrosesan tertentu.",
    "sec6i4": "Mengajukan keluhan kepada otoritas perlindungan data setempat Anda.",
    "sec7Title": "Keamanan",
    "sec7Body": "Lalu lintas antara aplikasi dan server kami dienkripsi saat transit, dan setiap tugas, tautan unduhan, serta karya diperiksa terhadap akun Anda yang telah masuk agar pihak lain tidak dapat membacanya. Kunci hanya disimpan di sisi server, dengan hak akses paling minimal. Tidak ada metode transmisi atau penyimpanan yang dapat dijamin sepenuhnya aman.",
    "sec8Title": "Perubahan kebijakan ini",
    "sec8Body": "Kami dapat memperbarui Kebijakan Privasi ini dari waktu ke waktu. Versi terbaru selalu diterbitkan di halaman ini, dan perubahan material akan diumumkan di dalam produk atau melalui cara lain yang sesuai sebelum berlaku.",
    "sec9Title": "Hubungi kami",
    "sec9Body": "Jika Anda memiliki pertanyaan, permintaan, atau keluhan mengenai Kebijakan Privasi ini atau data pribadi Anda, Anda dapat menghubungi kami melalui email:",
    "footerNote": "Terus menggunakan Melovar setelah pembaruan berarti Anda menerima versi Kebijakan Privasi ini yang berlaku saat itu.",
}

AR: dict[str, str] = {
    "sec1Title": "مقدمة",
    "sec1Body": "توضح سياسة الخصوصية هذه كيفية قيام Melovar بجمع بياناتك واستخدامها وتخزينها وحمايتها عند استخدامك خدمة إنشاء الموسيقى بالذكاء الاصطناعي. وبدخولك إلى المنصة أو استخدامك لها فإنك تقر بأنك قرأت هذه السياسة وفهمتها.",
    "sec2Title": "المعلومات التي نجمعها",
    "sec2Lead": "نجمع فقط ما يلزم لتشغيل الخدمة، وفقط عندما تقدمه أنت أو عندما ينشأ عن استخدامك:",
    "sec2i1": "معلومات الحساب – عنوان البريد الإلكتروني الذي تسجل به، واسم مستخدم اختياري، وقيمة العمر التي تُستخدم حصرًا لتطبيق شرط الحد الأدنى للسن.",
    "sec2i2": "محتوى الإنشاء – الطلبات (prompts) وكلمات الأغاني وبيانات المشروع التي ترسلها، والملفات الصوتية المتولدة منها.",
    "sec2i3": "البيانات التقنية وبيانات السجل – معلومات الجهاز والمتصفح، وعنوان IP، وسجلات الاستخدام، وتُستخدم لاستكشاف الأخطاء ولأغراض الأمن وتحسين الخدمة.",
    "sec2i4": "بيانات الطلب والمعاملة – الحد الأدنى اللازم لتسليم ما اشتريته: معرّفات الطلب/المعاملة، وحالة المعاملة، والعملة والمبلغ، وحزمة الأرصدة أو الخطة المشتراة. ولا تتضمن أبدًا بيانات بطاقة الدفع.",
    "sec2negLead": "لا نجمع:",
    "sec2neg1": "أرقام بطاقات الدفع الكاملة أو رموز CVV/CVC أو بيانات الحسابات المصرفية – إذ يتولى مزوّدنا الخارجي Paddle، بصفته تاجر السجل (Merchant of Record)، معالجة المدفوعات ويجمع هذه البيانات ويعالجها مباشرة؛ ولا تجمعها Melovar ولا تخزنها.",
    "sec3Title": "كيف نستخدم بياناتك",
    "sec3Lead": "لا تُستخدم بياناتك إلا للأغراض التالية:",
    "sec3i1": "تقديم الخدمة وصيانتها وتحسينها.",
    "sec3i2": "تشغيل عمليات إنشاء الموسيقى والأدوات الصوتية التي تطلبها.",
    "sec3i3": "تطبيق حدود الاستخدام ومنع إساءة الاستخدام والاحتيال والأعطال التقنية.",
    "sec3i4": "تشخيص الأخطاء وحماية الأمن والامتثال للالتزامات القانونية.",
    "sec3i5": "تسليم الأرصدة ومزايا الاشتراك التي اشتريتها، ولأغراض التسوية ودعم العملاء ومعالجة النزاعات.",
    "sec4Title": "التخزين والاحتفاظ",
    "sec4Body": "تُخزَّن سجلات الحساب والمشروع في قاعدة بيانات PostgreSQL نديرها؛ وتُخزَّن الملفات الصوتية في حاوية تخزين كائنات خاصة؛ وروابط التشغيل التي نمنحها هي روابط موقّعة قصيرة الأجل تنتهي صلاحيتها تلقائيًا. وتُعاد ضبط عدّادات الاستخدام يوميًا وشهريًا.",
    "sec4i1": "عند حذف مهمة أو عمل في My Creations، تُحذف معه ملفاته الصوتية وسجلاته المرتبطة.",
    "sec4i2": "تُحذف البيانات التي لم تعد لازمة أو تُجهَّل هويتها، ونعالج طلبات الحذف في حدود القانون المعمول به.",
    "sec4i3": "قد يحتفظ مزوّد مراقبة الأخطاء لدينا ببيانات تشخيصية لمدة محدودة.",
    "sec5Title": "المشاركة والأطراف الثالثة",
    "sec5Lead": "نحن لا نبيع بياناتك الشخصية. ولتقديم الخدمة يتعين علينا تمرير البيانات اللازمة إلى:",
    "sec5i1": "لتقديم إنشاء الموسيقى بالذكاء الاصطناعي والميزات المرتبطة به، قد نمرر مدخلات المستخدم التي تحتاج ميزة معينة إلى معالجتها — وهي عادةً الطلبات (prompts) وكلمات الأغاني، والصوت عند لزومه للميزة — إلى مزوّدي خدمات ذكاء اصطناعي خارجيين. والمزوّدون الذين يولّدون الصوت هم خدمات خارجية لإنشاء الموسيقى بالذكاء الاصطناعي، وهي حاليًا Yinchao v4.0 و TemPolor tempolor-latest. أما مزوّدو المساعدة النصية — تحسين الطلبات والمعالجة المتعلقة بكلمات الأغاني — فهم حاليًا Agnes AI agnes-2.0-flash و Google Gemini gemini-2.0-flash، مع توافر NVIDIA كقدرة معالجة نصية إضافية؛ وكلها نماذج نصية لا تولّد ملف الصوت الموسيقي النهائي. ويعتمد المزوّد المستخدم فعليًا على الميزة وتوافرها وإعدادات نظامنا، ويتلقى كل منهم المدخلات اللازمة للوظيفة التي يؤديها. وتُستخدم أسماء النماذج المذكورة أعلاه لتحديد الخدمات التي نستدعيها، ويدير كل مزوّد نماذجه وبيانات تدريبه وبنيته التحتية بنفسه. وقد يتغير مزوّدو خدمات الذكاء الاصطناعي الخارجيون وإصدارات النماذج التي يقدمونها مع تطور ميزات منتجنا أو المتطلبات التقنية أو مدى توافر الخدمة؛ وسيُبلَّغ عن التغييرات الجوهرية عبر تحديث هذه السياسة وأي إشعار آخر يقتضيه القانون المعمول به.",
    "sec5i2": "مزوّدو البنية التحتية والاستضافة والتخزين ومراقبة الأخطاء الذين يشغّلون المنصة نيابةً عنا.",
    "sec5i3": "الجهات الرسمية، عند اقتضاء القانون أو طلب قانوني صحيح؛ أو الخلف في حال الاندماج أو نقل الأصول، ويظل ملتزمًا بهذه السياسة.",
    "sec5i4": "مزوّد الدفع لدينا Paddle، الذي يعمل بصفته تاجر السجل (Merchant of Record) للمدفوعات والإيصالات والفواتير والاسترداد والضرائب المرتبطة بها، ويجمع بيانات الدفع الخاصة بك مباشرة.",
    "sec6Title": "حقوقك",
    "sec6Lead": "مع مراعاة قوانين حماية البيانات المعمول بها، يمكنك:",
    "sec6i1": "الاطلاع على البيانات التي نحتفظ بها عنك والحصول على نسخة منها.",
    "sec6i2": "تصحيح البيانات غير الدقيقة، وحذف بياناتك أو أعمالك حيثما يسمح القانون.",
    "sec6i3": "سحب الموافقة على المعالجة، أو الاعتراض على معالجة معينة أو تقييدها.",
    "sec6i4": "تقديم شكوى إلى هيئة حماية البيانات المحلية لديك.",
    "sec7Title": "الأمن",
    "sec7Body": "تُشفَّر حركة البيانات بين التطبيق وخوادمنا أثناء النقل، ويُتحقق من كل مهمة ورابط تنزيل وعمل مقابل حسابك المسجَّل دخوله حتى لا يتمكن الآخرون من قراءتها. وتُحفظ المفاتيح على جانب الخادم فقط، وفق مبدأ أقل صلاحية. ولا يمكن ضمان أي وسيلة نقل أو تخزين بأنها آمنة تمامًا.",
    "sec8Title": "التغييرات على هذه السياسة",
    "sec8Body": "قد نحدّث سياسة الخصوصية هذه من وقت لآخر. وتُنشر النسخة السارية دائمًا على هذه الصفحة، وسيُعلَن عن التغييرات الجوهرية داخل المنتج أو بأي وسيلة مناسبة أخرى قبل سريانها.",
    "sec9Title": "اتصل بنا",
    "sec9Body": "إذا كان لديك سؤال أو طلب أو شكوى بشأن سياسة الخصوصية هذه أو بشأن بياناتك الشخصية، يمكنك التواصل معنا عبر البريد الإلكتروني:",
    "footerNote": "استمرارك في استخدام Melovar بعد أي تحديث يعني موافقتك على النسخة السارية من سياسة الخصوصية هذه.",
}

TRANSLATIONS = {"hi": HI, "id": ID, "ar": AR}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写入")
    args = ap.parse_args()

    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    en_legal = en["legal"]
    en_privacy = en_legal["privacy"]
    order = list(en_privacy.keys())

    problems: list[str] = []
    for lang in LANGS:
        table = TRANSLATIONS[lang]
        expected = [k for k in order if k != "contactEmail"]
        missing = [k for k in expected if k not in table]
        extra = [k for k in table if k not in expected]
        if missing:
            problems.append(f"{lang}: 缺译 {missing}")
        if extra:
            problems.append(f"{lang}: 多余键 {extra}")
        empty = [k for k, v in table.items() if not str(v).strip()]
        if empty:
            problems.append(f"{lang}: 空值 {empty}")
        # 与英文完全同值 = 大概率漏译（contactEmail 除外）
        same = [k for k, v in table.items() if en_privacy.get(k) == v]
        if same:
            problems.append(f"{lang}: 与英文同值（疑似未译）{same}")

    if problems:
        print("前置校验失败：")
        for p in problems:
            print("  -", p)
        return 1
    print(f"前置校验通过：hi/id/ar 各 {len(order) - 1} 条译文齐全、无空值、无与英文同值")
    if args.check:
        return 0

    for lang in LANGS:
        path = LOCALES / f"{lang}.json"
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        legal = data["legal"]

        # 按 en 的键序重建 privacy（含未翻译的 contactEmail）
        rebuilt: dict[str, str] = {}
        for key in order:
            if key == "contactEmail":
                rebuilt[key] = en_privacy[key]
            else:
                rebuilt[key] = TRANSLATIONS[lang][key]

        # privacy 在 legal 中的位置也对齐 en（en 里它排在最后）
        legal["privacy"] = rebuilt

        out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        path.write_text(out, encoding="utf-8")
        print(f"  {lang}.json 已写入 legal.privacy（{len(rebuilt)} 键，文件 {len(raw)} -> {len(out)} 字节）")

    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
