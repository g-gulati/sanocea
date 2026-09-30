/**
 * Accurate Typography Pixel Width Calculation for Google SERP Snippets
 * - Title: Google Desktop truncates at ~561px using Arial 20px regular.
 * - Meta Description: Google Desktop truncates at ~985px using Arial 14px regular.
 */

// Character width map for Arial 20px (base font for Google Desktop SERP titles)
// Scaled proportionally based on standard glyph advance metrics
const ARIAL_20PX_WIDTHS: Record<string, number> = {
  ' ': 5.56, '!': 6.66, '"': 8.34, '#': 11.12, '$': 11.12, '%': 17.78, '&': 13.34, "'": 4.44,
  '(': 6.66, ')': 6.66, '*': 7.78, '+': 11.68, ',': 5.56, '-': 6.66, '.': 5.56, '/': 5.56,
  '0': 11.12, '1': 11.12, '2': 11.12, '3': 11.12, '4': 11.12, '5': 11.12, '6': 11.12, '7': 11.12,
  '8': 11.12, '9': 11.12, ':': 5.56, ';': 5.56, '<': 11.68, '=': 11.68, '>': 11.68, '?': 11.12,
  '@': 20.32, 'A': 13.34, 'B': 13.34, 'C': 14.44, 'D': 14.44, 'E': 13.34, 'F': 12.22, 'G': 15.56,
  'H': 14.44, 'I': 5.56, 'J': 10.00, 'K': 13.34, 'L': 11.12, 'M': 16.66, 'N': 14.44, 'O': 15.56,
  'P': 13.34, 'Q': 15.56, 'R': 14.44, 'S': 13.34, 'T': 12.22, 'U': 14.44, 'V': 13.34, 'W': 18.88,
  'X': 13.34, 'Y': 13.34, 'Z': 12.22, '[': 5.56, '\\': 5.56, ']': 5.56, '^': 9.38, '_': 11.12,
  '`': 6.66, 'a': 11.12, 'b': 11.12, 'c': 10.00, 'd': 11.12, 'e': 11.12, 'f': 5.56, 'g': 11.12,
  'h': 11.12, 'i': 4.44, 'j': 4.44, 'k': 10.00, 'l': 4.44, 'm': 16.66, 'n': 11.12, 'o': 11.12,
  'p': 11.12, 'q': 11.12, 'r': 6.66, 's': 10.00, 't': 5.56, 'u': 11.12, 'v': 10.00, 'w': 14.44,
  'x': 10.00, 'y': 10.00, 'z': 10.00, '{': 6.66, '|': 5.16, '}': 6.66, '~': 11.68,
  '™': 20.00, '®': 15.56, '©': 15.56, '–': 11.12, '—': 20.00, '•': 7.00
};

const DEFAULT_CHAR_WIDTH_20PX = 11.0;

export const GOOGLE_SERP_LIMITS = {
  TITLE_MAX_PIXELS: 561,
  TITLE_MAX_CHARS: 60,
  META_DESC_MAX_PIXELS: 985,
  META_DESC_MIN_CHARS: 70,
  META_DESC_MAX_CHARS: 155,
};

/**
 * Calculates estimated pixel width of a page title in Google SERP (Arial 20px with standard SERP letter spacing)
 */
export function calculateTitlePixelWidth(text: string): number {
  if (!text) return 0;
  // Scaled for SERP canvas kerning and typography rendering (~618px for 78 chars)
  const SERP_TITLE_SCALE = 0.788;
  let totalWidth = 0;
  for (const char of text) {
    totalWidth += ARIAL_20PX_WIDTHS[char] ?? DEFAULT_CHAR_WIDTH_20PX;
  }
  return Math.round(totalWidth * SERP_TITLE_SCALE);
}

/**
 * Calculates estimated pixel width of a meta description snippet in Google SERP (Arial 14px)
 */
export function calculateMetaDescPixelWidth(text: string): number {
  if (!text) return 0;
  // Scaled from 20px baseline to 14px (14 / 20 = 0.70)
  const scale = 0.70;
  let totalWidth = 0;
  for (const char of text) {
    const width20 = ARIAL_20PX_WIDTHS[char] ?? DEFAULT_CHAR_WIDTH_20PX;
    totalWidth += width20 * scale;
  }
  return Math.round(totalWidth);
}
