/**
 * SANOCEA SEO Stack — Google Merchant Center Feed Ingestion Engine
 * Ingests Google Merchant Center TSV (tab-separated) and XML (Google RSS 2.0 / Atom) feeds.
 */

import * as cheerio from 'cheerio';

export interface GmcFeedProduct {
  id: string;
  title: string;
  description?: string;
  link: string;
  imageLink?: string;
  availability: 'in_stock' | 'out_of_stock' | 'preorder';
  price: number;
  salePrice?: number;
  currency: string;
  brand?: string;
  gtin?: string;
  mpn?: string;
}

/**
 * Parses numeric price and currency string (e.g. "2499.00 INR" -> { price: 2499, currency: "INR" })
 */
export function parseGmcPrice(priceStr: string): { price: number; currency: string } {
  if (!priceStr) return { price: 0, currency: 'INR' };
  const clean = priceStr.trim();
  const match = clean.match(/^([\d,.]+)\s*([A-Za-z]{3})?$/) || clean.match(/^([A-Za-z]{3})?\s*([\d,.]+)$/);
  if (match) {
    const rawNum = (match[1].match(/[\d.]/) ? match[1] : match[2]).replace(/,/g, '');
    const currency = (match[1].match(/^[A-Za-z]{3}$/) ? match[1] : match[2]) || 'INR';
    return {
      price: parseFloat(rawNum) || 0,
      currency: currency.toUpperCase()
    };
  }
  const numOnly = parseFloat(clean.replace(/[^\d.]/g, '')) || 0;
  return { price: numOnly, currency: 'INR' };
}

/**
 * Normalizes availability status to standard GMC values
 */
export function normalizeGmcAvailability(availStr: string): 'in_stock' | 'out_of_stock' | 'preorder' {
  const lower = (availStr || '').toLowerCase().trim();
  if (lower.includes('out') || lower.includes('sold') || lower.includes('backorder')) {
    return 'out_of_stock';
  }
  if (lower.includes('pre')) {
    return 'preorder';
  }
  return 'in_stock';
}

/**
 * Parses a TSV Google Merchant Center text feed
 */
export function parseGmcTsvFeed(tsvContent: string): GmcFeedProduct[] {
  const lines = tsvContent.split(/\r?\n/).filter(line => line.trim().length > 0);
  if (lines.length < 2) return [];

  const headers = lines[0].split('\t').map(h => h.trim().toLowerCase());
  const products: GmcFeedProduct[] = [];

  const getCol = (rowCols: string[], targetHeader: string): string => {
    const idx = headers.indexOf(targetHeader);
    return idx !== -1 && idx < rowCols.length ? rowCols[idx].trim() : '';
  };

  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split('\t');
    const id = getCol(cols, 'id') || `SKU-${i}`;
    const link = getCol(cols, 'link');
    if (!link) continue;

    const title = getCol(cols, 'title') || 'Untitled Product';
    const rawPrice = getCol(cols, 'price');
    const rawSalePrice = getCol(cols, 'sale_price');
    const { price, currency } = parseGmcPrice(rawPrice);
    const saleParsed = rawSalePrice ? parseGmcPrice(rawSalePrice).price : undefined;

    products.push({
      id,
      title,
      description: getCol(cols, 'description'),
      link,
      imageLink: getCol(cols, 'image_link'),
      availability: normalizeGmcAvailability(getCol(cols, 'availability')),
      price,
      salePrice: saleParsed,
      currency,
      brand: getCol(cols, 'brand'),
      gtin: getCol(cols, 'gtin'),
      mpn: getCol(cols, 'mpn')
    });
  }

  return products;
}

/**
 * Parses an XML Google Merchant Center RSS 2.0 / Atom feed
 */
export function parseGmcXmlFeed(xmlContent: string): GmcFeedProduct[] {
  const $ = cheerio.load(xmlContent, { xmlMode: true });
  const products: GmcFeedProduct[] = [];

  $('item, entry').each((i, el) => {
    const $item = $(el);

    // Google XML attributes use <g:attr> or standard <attr>
    const id = $item.find('g\\:id, id').text().trim() || `SKU-${i + 1}`;
    const link = $item.find('g\\:link, link').text().trim() || $item.find('link').attr('href')?.trim() || '';
    if (!link) return;

    const title = $item.find('g\\:title, title').text().trim() || 'Untitled Product';
    const description = $item.find('g\\:description, description').text().trim();
    const rawPrice = $item.find('g\\:price, price').text().trim();
    const rawSalePrice = $item.find('g\\:sale_price, sale_price').text().trim();
    const { price, currency } = parseGmcPrice(rawPrice);
    const saleParsed = rawSalePrice ? parseGmcPrice(rawSalePrice).price : undefined;

    const rawAvail = $item.find('g\\:availability, availability').text().trim();
    const brand = $item.find('g\\:brand, brand').text().trim();
    const gtin = $item.find('g\\:gtin, gtin').text().trim();
    const mpn = $item.find('g\\:mpn, mpn').text().trim();
    const imageLink = $item.find('g\\:image_link, image_link').text().trim();

    products.push({
      id,
      title,
      description,
      link,
      imageLink,
      availability: normalizeGmcAvailability(rawAvail),
      price,
      salePrice: saleParsed,
      currency,
      brand,
      gtin,
      mpn
    });
  });

  return products;
}

/**
 * Ingests a GMC feed automatically identifying whether it is XML or TSV
 */
export function parseGmcFeed(content: string): GmcFeedProduct[] {
  const trimmed = content.trim();
  if (trimmed.startsWith('<?xml') || trimmed.startsWith('<rss') || trimmed.startsWith('<feed')) {
    return parseGmcXmlFeed(trimmed);
  }
  return parseGmcTsvFeed(trimmed);
}
