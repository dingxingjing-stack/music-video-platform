export interface PhoneCountry {
  code: string;
  name: string;
  dialCode: string;
}

// Zyvexo Phone OTP 第一版全球白名单；与 UI 语言列表无关。
export const PHONE_COUNTRIES: PhoneCountry[] = [
  { code: 'US', name: 'United States', dialCode: '+1' },
  { code: 'CA', name: 'Canada', dialCode: '+1' },
  { code: 'GB', name: 'United Kingdom', dialCode: '+44' },
  { code: 'AU', name: 'Australia', dialCode: '+61' },
  { code: 'NZ', name: 'New Zealand', dialCode: '+64' },
  { code: 'IE', name: 'Ireland', dialCode: '+353' },
  { code: 'SG', name: 'Singapore', dialCode: '+65' },
  { code: 'ES', name: 'Spain', dialCode: '+34' },
  { code: 'MX', name: 'Mexico', dialCode: '+52' },
  { code: 'AR', name: 'Argentina', dialCode: '+54' },
  { code: 'CO', name: 'Colombia', dialCode: '+57' },
  { code: 'CL', name: 'Chile', dialCode: '+56' },
  { code: 'PE', name: 'Peru', dialCode: '+51' },
  { code: 'EC', name: 'Ecuador', dialCode: '+593' },
  { code: 'FR', name: 'France', dialCode: '+33' },
  { code: 'BE', name: 'Belgium', dialCode: '+32' },
  { code: 'CH', name: 'Switzerland', dialCode: '+41' },
  { code: 'DE', name: 'Germany', dialCode: '+49' },
  { code: 'AT', name: 'Austria', dialCode: '+43' },
  { code: 'CN', name: 'China', dialCode: '+86' },
  { code: 'JP', name: 'Japan', dialCode: '+81' },
  { code: 'KR', name: 'South Korea', dialCode: '+82' },
  { code: 'PT', name: 'Portugal', dialCode: '+351' },
  { code: 'AO', name: 'Angola', dialCode: '+244' },
  { code: 'MZ', name: 'Mozambique', dialCode: '+258' },
  { code: 'RU', name: 'Russia', dialCode: '+7' },
  { code: 'KZ', name: 'Kazakhstan', dialCode: '+7' },
  { code: 'NL', name: 'Netherlands', dialCode: '+31' },
  { code: 'IT', name: 'Italy', dialCode: '+39' },
  { code: 'IL', name: 'Israel', dialCode: '+972' },
];
