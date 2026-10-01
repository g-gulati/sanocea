/**
 * Readable text in the server-delivered HTML: what a crawler that does not run JavaScript can read.
 * One definition shared by the thin-content observer and the published-page audit so both always agree.
 */
export function staticVisibleText($: any): string {
  const bodyClone = $('body').clone();
  bodyClone.find('script, style, nav, footer, header, noscript, svg').remove();
  // cheerio's .text() joins adjacent elements without a separator ("<p>a</p><p>b</p>" -> "ab"), which undercounts
  // words and over-reports thin pages. Close every element with a space so element boundaries are word boundaries.
  bodyClone.find('*').append(' ');
  return bodyClone.text().replace(/\s+/g, ' ').trim();
}

export function countWords(text: string): number {
  return text ? text.split(' ').filter(Boolean).length : 0;
}

/** Every word of body text in the delivered HTML (navigation and header included; scripts, styles, noscript, svg excluded). */
export function staticBodyWordCount($: any): number {
  const bodyClone = $('body').clone();
  bodyClone.find('script, style, noscript, svg').remove();
  bodyClone.find('*').append(' ');
  return countWords(bodyClone.text().replace(/\s+/g, ' ').trim());
}
