import fs from 'node:fs';
import crypto from 'node:crypto';

async function main() {
  const credPath = '/etc/sanocea/gsc_service_account.json';
  console.log(`=== 1. Checking credential file at ${credPath} ===`);
  if (!fs.existsSync(credPath)) {
    console.error('FAIL: Credential file does not exist');
    process.exit(1);
  }
  const stat = fs.statSync(credPath);
  console.log(`PASS: Credential file exists. Size: ${stat.size} bytes, Mode: ${stat.mode.toString(8)}`);

  const cred = JSON.parse(fs.readFileSync(credPath, 'utf8'));
  console.log(`Client Email: ${cred.client_email}`);
  console.log(`Project ID: ${cred.project_id}`);

  console.log('\n=== 2. Testing Service Account JWT Authentication ===');
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: 'RS256', typ: 'JWT' };
  const payload = {
    iss: cred.client_email,
    scope: 'https://www.googleapis.com/auth/webmasters.readonly',
    aud: 'https://oauth2.googleapis.com/token',
    exp: now + 3600,
    iat: now
  };

  const b64Header = Buffer.from(JSON.stringify(header)).toString('base64url');
  const b64Payload = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const sign = crypto.createSign('RSA-SHA256');
  sign.update(`${b64Header}.${b64Payload}`);
  const signature = sign.sign(cred.private_key, 'base64url');
  const assertion = `${b64Header}.${b64Payload}.${signature}`;

  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion
    })
  });

  const tokenData = await tokenRes.json();
  if (!tokenRes.ok || !tokenData.access_token) {
    console.error(`FAIL: Token exchange failed (${tokenRes.status}):`, tokenData);
    process.exit(1);
  }
  console.log(`PASS: Token exchange succeeded (HTTP ${tokenRes.status}). Token type: ${tokenData.token_type}, expires_in: ${tokenData.expires_in}s`);
  const accessToken = tokenData.access_token;

  console.log('\n=== 3 & 4. Calling Google Search Console Sites API ===');
  const sitesRes = await fetch('https://www.googleapis.com/webmasters/v3/sites', {
    headers: { Authorization: `Bearer ${accessToken}` }
  });
  const sitesData = await sitesRes.json();
  console.log(`Sites API HTTP Status: ${sitesRes.status}`);
  console.log('Sites API Response:', JSON.stringify(sitesData, null, 2));

  const targetSite = sitesData.siteEntry?.find(s => s.siteUrl === 'sc-domain:sanocea.com');
  if (!targetSite) {
    console.error('FAIL: sc-domain:sanocea.com not found in siteEntry list');
    process.exit(1);
  }
  console.log(`PASS: Found property sc-domain:sanocea.com with permissionLevel: "${targetSite.permissionLevel}"`);

  console.log('\n=== 5 & 6. Executing Search Analytics Query against sc-domain:sanocea.com ===');
  const endDate = new Date().toISOString().slice(0, 10);
  const startDateObj = new Date();
  startDateObj.setDate(startDateObj.getDate() - 28);
  const startDate = startDateObj.toISOString().slice(0, 10);
  console.log(`Date range queried: ${startDate} to ${endDate}`);

  // Query 1: Overall aggregates
  const queryRes = await fetch(`https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent('sc-domain:sanocea.com')}/searchAnalytics/query`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      startDate,
      endDate,
      dimensions: ['date']
    })
  });
  console.log(`Search Analytics Query (by date) HTTP Status: ${queryRes.status}`);
  const queryData = await queryRes.json();
  console.log('Search Analytics Data by date:', JSON.stringify(queryData, null, 2));

  // Query 2: By page
  const pageRes = await fetch(`https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent('sc-domain:sanocea.com')}/searchAnalytics/query`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      startDate,
      endDate,
      dimensions: ['page']
    })
  });
  console.log(`Search Analytics Query (by page) HTTP Status: ${pageRes.status}`);
  const pageData = await pageRes.json();
  console.log('Search Analytics Data by page:', JSON.stringify(pageData, null, 2));

  // Query 3: By device
  const deviceRes = await fetch(`https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent('sc-domain:sanocea.com')}/searchAnalytics/query`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      startDate,
      endDate,
      dimensions: ['device']
    })
  });
  console.log(`Search Analytics Query (by device) HTTP Status: ${deviceRes.status}`);
  const deviceData = await deviceRes.json();
  console.log('Search Analytics Data by device:', JSON.stringify(deviceData, null, 2));
}

main().catch(err => {
  console.error('Fatal error during verification:', err);
  process.exit(1);
});
