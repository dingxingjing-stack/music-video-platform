/**
 * P3-3: 多语言扩充翻译文件 (14 种语言)
 * 新增：德语/意大利语/葡萄牙语/俄语/印地语/泰语/越南语/印尼语
 */

import type { Translation } from './types';

export const additionalTranslations: Partial<Record<string, Translation>> = {
  // 德语 (de-DE)
  'de-DE': {
    common: {
      appName: 'Hermes Musik Plattform',
      welcome: 'Willkommen',
      loading: 'Lädt...',
      save: 'Speichern',
      cancel: 'Abbrechen',
      delete: 'Löschen',
      edit: 'Bearbeiten',
      create: 'Erstellen',
      search: 'Suchen',
      settings: 'Einstellungen',
    },
    music: {
      generate: 'Generieren',
      play: 'Abspielen',
      pause: 'Pause',
      stop: 'Stoppen',
      record: 'Aufnehmen',
      export: 'Exportieren',
      import: 'Importieren',
      tempo: 'Tempo',
      key: 'Tonart',
      scale: 'Skala',
    },
    effects: {
      reverb: 'Hall',
      delay: 'Verzögerung',
      chorus: 'Chorus',
      eq: 'Equalizer',
      compressor: 'Kompressor',
    },
  },

  // 意大利语 (it-IT)
  'it-IT': {
    common: {
      appName: 'Piattaforma Musicale Hermes',
      welcome: 'Benvenuto',
      loading: 'Caricamento...',
      save: 'Salva',
      cancel: 'Annulla',
      delete: 'Elimina',
      edit: 'Modifica',
      create: 'Crea',
      search: 'Cerca',
      settings: 'Impostazioni',
    },
    music: {
      generate: 'Genera',
      play: 'Riproduci',
      pause: 'Pausa',
      stop: 'Ferma',
      record: 'Registra',
      export: 'Esporta',
      import: 'Importa',
      tempo: 'Tempo',
      key: 'Tonalità',
      scale: 'Scala',
    },
    effects: {
      reverb: 'Riverbero',
      delay: 'Ritardo',
      chorus: 'Coro',
      eq: 'Equalizzatore',
      compressor: 'Compressore',
    },
  },

  // 葡萄牙语 (pt-BR)
  'pt-BR': {
    common: {
      appName: 'Plataforma Musical Hermes',
      welcome: 'Bem-vindo',
      loading: 'Carregando...',
      save: 'Salvar',
      cancel: 'Cancelar',
      delete: 'Excluir',
      edit: 'Editar',
      create: 'Criar',
      search: 'Buscar',
      settings: 'Configurações',
    },
    music: {
      generate: 'Gerar',
      play: 'Reproduzir',
      pause: 'Pausar',
      stop: 'Parar',
      record: 'Gravar',
      export: 'Exportar',
      import: 'Importar',
      tempo: 'Andamento',
      key: 'Tonalidade',
      scale: 'Escala',
    },
    effects: {
      reverb: 'Reverb',
      delay: 'Delay',
      chorus: 'Chorus',
      eq: 'Equalizador',
      compressor: 'Compressor',
    },
  },

  // 俄语 (ru-RU)
  'ru-RU': {
    common: {
      appName: 'Музыкальная платформа Hermes',
      welcome: 'Добро пожаловать',
      loading: 'Загрузка...',
      save: 'Сохранить',
      cancel: 'Отмена',
      delete: 'Удалить',
      edit: 'Редактировать',
      create: 'Создать',
      search: 'Поиск',
      settings: 'Настройки',
    },
    music: {
      generate: 'Генерировать',
      play: 'Воспроизвести',
      pause: 'Пауза',
      stop: 'Стоп',
      record: 'Записать',
      export: 'Экспорт',
      import: 'Импорт',
      tempo: 'Темп',
      key: 'Тональность',
      scale: 'Гамма',
    },
    effects: {
      reverb: 'Реверберация',
      delay: 'Задержка',
      chorus: 'Хорус',
      eq: 'Эквалайзер',
      compressor: 'Компрессор',
    },
  },

  // 印地语 (hi-IN)
  'hi-IN': {
    common: {
      appName: 'हर्मस संगीत मंच',
      welcome: 'स्वागत है',
      loading: 'लोड हो रहा है...',
      save: 'सहेजें',
      cancel: 'रद्द करें',
      delete: 'हटाएं',
      edit: 'संपादित करें',
      create: 'बनाएं',
      search: 'खोजें',
      settings: 'सेटिंग्स',
    },
    music: {
      generate: 'जनरेट करें',
      play: 'चलाएं',
      pause: 'रोकें',
      stop: 'बंद करें',
      record: 'रिकॉर्ड करें',
      export: 'निर्यात',
      import: 'आयात',
      tempo: 'लय',
      key: 'कुंजी',
      scale: 'पैमाना',
    },
    effects: {
      reverb: 'रिवर्ब',
      delay: 'देरी',
      chorus: 'कोरस',
      eq: 'इक्वलराइज़र',
      compressor: 'कंप्रेसर',
    },
  },

  // 泰语 (th-TH)
  'th-TH': {
    common: {
      appName: 'แพลตฟอร์มดนตรี Hermes',
      welcome: 'ยินดีต้อนรับ',
      loading: 'กำลังโหลด...',
      save: 'บันทึก',
      cancel: 'ยกเลิก',
      delete: 'ลบ',
      edit: 'แก้ไข',
      create: 'สร้าง',
      search: 'ค้นหา',
      settings: 'การตั้งค่า',
    },
    music: {
      generate: 'สร้าง',
      play: 'เล่น',
      pause: 'หยุดชั่วคราว',
      stop: 'หยุด',
      record: 'บันทึก',
      export: 'ส่งออก',
      import: 'นำเข้า',
      tempo: 'จังหวะ',
      key: 'คีย์',
      scale: 'สเกล',
    },
    effects: {
      reverb: 'รีเวิร์บ',
      delay: 'ดีเลย์',
      chorus: 'คอรัส',
      eq: 'อีควอไลเซอร์',
      compressor: 'คอมเพรสเซอร์',
    },
  },

  // 越南语 (vi-VN)
  'vi-VN': {
    common: {
      appName: 'Nền tảng Âm nhạc Hermes',
      welcome: 'Chào mừng',
      loading: 'Đang tải...',
      save: 'Lưu',
      cancel: 'Hủy',
      delete: 'Xóa',
      edit: 'Chỉnh sửa',
      create: 'Tạo',
      search: 'Tìm kiếm',
      settings: 'Cài đặt',
    },
    music: {
      generate: 'Tạo',
      play: 'Phát',
      pause: 'Tạm dừng',
      stop: 'Dừng',
      record: 'Ghi âm',
      export: 'Xuất',
      import: 'Nhập',
      tempo: 'Nhịp độ',
      key: 'Giọng',
      scale: 'Thang âm',
    },
    effects: {
      reverb: 'Reverb',
      delay: 'Delay',
      chorus: 'Chorus',
      eq: 'Equalizer',
      compressor: 'Compressor',
    },
  },

  // 印尼语 (id-ID)
  'id-ID': {
    common: {
      appName: 'Platform Musik Hermes',
      welcome: 'Selamat Datang',
      loading: 'Memuat...',
      save: 'Simpan',
      cancel: 'Batal',
      delete: 'Hapus',
      edit: 'Edit',
      create: 'Buat',
      search: 'Cari',
      settings: 'Pengaturan',
    },
    music: {
      generate: 'Hasilkan',
      play: 'Putar',
      pause: 'Jeda',
      stop: 'Berhenti',
      record: 'Rekam',
      export: 'Ekspor',
      import: 'Impor',
      tempo: 'Tempo',
      key: 'Nada Dasar',
      scale: 'Skala',
    },
    effects: {
      reverb: 'Reverb',
      delay: 'Delay',
      chorus: 'Chorus',
      eq: 'Equalizer',
      compressor: 'Compressor',
    },
  },
};

export default additionalTranslations;