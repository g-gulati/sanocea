/**
 * SANOCEA SEO Stack — Google Search Console Authentication & Verification Engine
 * 
 * Supports:
 * 1. Service Account M2M authentication with native JWT assertion signing (node:crypto)
 * 2. OAuth 2.0 Web flow for client-owned properties
 * 3. Property verification and permission inspection
 * 4. Deterministic Mock/Fixture mode for offline audits and test pipelines
 * 5. Graceful fallback when uncredentialed ([REQUIRES_ACCESS])
 */

import * as crypto from 'node:crypto';
import { GscPropertyVerification } from '../core/types.js';

export interface ServiceAccountCredentials {
  client_email: string;
  private_key: string;
  project_id?: string;
}

export interface OAuthCredentials {
  clientId: string;
  clientSecret: string;
  refreshToken?: string;
  accessToken?: string;
  redirectUri?: string;
}

export interface GscAuthConfig {
  authType: 'SERVICE_ACCOUNT' | 'OAUTH_2' | 'MOCK_FIXTURE' | 'NONE';
  serviceAccount?: ServiceAccountCredentials;
  oauth?: OAuthCredentials;
  mockVerification?: Partial<GscPropertyVerification>;
}

export class GscAuthManager {
  private config: GscAuthConfig;
  private cachedToken: { token: string; expiresAt: number } | null = null;

  constructor(config: GscAuthConfig) {
    this.config = config;
  }

  /**
   * Generates a Google OAuth authorization URL for client-owned properties
   */
  public generateAuthUrl(state?: string): string {
    if (this.config.authType !== 'OAUTH_2' || !this.config.oauth) {
      throw new Error('OAuth 2.0 credentials not configured');
    }
    const params = new URLSearchParams({
      client_id: this.config.oauth.clientId,
      redirect_uri: this.config.oauth.redirectUri || 'https://sanocea.com/oauth/callback',
      response_type: 'code',
      scope: 'https://www.googleapis.com/auth/webmasters.readonly',
      access_type: 'offline',
      prompt: 'consent'
    });
    if (state) params.set('state', state);
    return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  }

  /**
   * Exchanges an authorization code for access and refresh tokens
   */
  public async exchangeCodeForTokens(code: string): Promise<{ accessToken: string; refreshToken: string; expiresIn: number }> {
    if (this.config.authType !== 'OAUTH_2' || !this.config.oauth) {
      throw new Error('OAuth 2.0 credentials not configured');
    }

    const resp = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: this.config.oauth.clientId,
        client_secret: this.config.oauth.clientSecret,
        redirect_uri: this.config.oauth.redirectUri || 'https://sanocea.com/oauth/callback',
        grant_type: 'authorization_code'
      })
    });

    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(`Failed to exchange authorization code: ${err}`);
    }

    const data = await resp.json() as any;
    return {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresIn: data.expires_in
    };
  }

  /**
   * Generates a signed JWT assertion for Google Service Account authentication
   */
  private generateServiceAccountJwt(): string {
    if (!this.config.serviceAccount) {
      throw new Error('Service account credentials not provided');
    }

    const now = Math.floor(Date.now() / 1000);
    const header = {
      alg: 'RS256',
      typ: 'JWT'
    };

    const claimSet = {
      iss: this.config.serviceAccount.client_email,
      scope: 'https://www.googleapis.com/auth/webmasters.readonly',
      aud: 'https://oauth2.googleapis.com/token',
      exp: now + 3600,
      iat: now
    };

    const b64UrlHeader = Buffer.from(JSON.stringify(header)).toString('base64url');
    const b64UrlClaims = Buffer.from(JSON.stringify(claimSet)).toString('base64url');
    const unsignedToken = `${b64UrlHeader}.${b64UrlClaims}`;

    const signer = crypto.createSign('RSA-SHA256');
    signer.update(unsignedToken);
    const signature = signer.sign(this.config.serviceAccount.private_key, 'base64url');

    return `${unsignedToken}.${signature}`;
  }

  /**
   * Retrieves a valid Google API access token
   */
  public async getAccessToken(): Promise<string | null> {
    if (this.config.authType === 'NONE') {
      return null;
    }

    if (this.config.authType === 'MOCK_FIXTURE') {
      return 'mock-gsc-access-token';
    }

    if (this.cachedToken && this.cachedToken.expiresAt > Date.now() + 60000) {
      return this.cachedToken.token;
    }

    if (this.config.authType === 'SERVICE_ACCOUNT' && this.config.serviceAccount) {
      const jwt = this.generateServiceAccountJwt();
      const resp = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
          assertion: jwt
        })
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`Google Service Account token exchange failed: ${err}`);
      }

      const data = await resp.json() as any;
      this.cachedToken = {
        token: data.access_token,
        expiresAt: Date.now() + (data.expires_in * 1000)
      };
      return this.cachedToken.token;
    }

    if (this.config.authType === 'OAUTH_2' && this.config.oauth?.refreshToken) {
      const resp = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: this.config.oauth.clientId,
          client_secret: this.config.oauth.clientSecret,
          refresh_token: this.config.oauth.refreshToken,
          grant_type: 'refresh_token'
        })
      });

      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(`OAuth 2.0 token refresh failed: ${err}`);
      }

      const data = await resp.json() as any;
      this.cachedToken = {
        token: data.access_token,
        expiresAt: Date.now() + (data.expires_in * 1000)
      };
      return this.cachedToken.token;
    }

    return null;
  }

  /**
   * Verifies property ownership and permission level for a given site URL
   */
  public async verifyProperty(siteUrl: string): Promise<GscPropertyVerification> {
    if (this.config.authType === 'MOCK_FIXTURE') {
      return {
        siteUrl,
        verified: true,
        permissionLevel: this.config.mockVerification?.permissionLevel || 'siteOwner',
        authMethod: 'MOCK_FIXTURE'
      };
    }

    if (this.config.authType === 'NONE') {
      return {
        siteUrl,
        verified: false,
        permissionLevel: 'siteUnverified',
        authMethod: 'NONE',
        errorMessage: 'Google Search Console not connected [REQUIRES_ACCESS]'
      };
    }

    try {
      const token = await this.getAccessToken();
      if (!token) {
        return {
          siteUrl,
          verified: false,
          permissionLevel: 'siteUnverified',
          authMethod: this.config.authType,
          errorMessage: 'Authentication token unavailable'
        };
      }

      // Check property permission via GSC Sites API
      const encodedUrl = encodeURIComponent(siteUrl);
      const resp = await fetch(`https://www.googleapis.com/webmasters/v3/sites/${encodedUrl}`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (!resp.ok) {
        if (resp.status === 403 || resp.status === 404) {
          return {
            siteUrl,
            verified: false,
            permissionLevel: 'siteUnverified',
            authMethod: this.config.authType,
            errorMessage: 'User or Service Account does not have verified access to this GSC property'
          };
        }
        return {
          siteUrl,
          verified: false,
          permissionLevel: 'siteUnverified',
          authMethod: this.config.authType,
          errorMessage: `Google API HTTP ${resp.status}: ${resp.statusText}`
        };
      }

      const siteData = await resp.json() as any;
      return {
        siteUrl,
        verified: true,
        permissionLevel: (siteData.permissionLevel as any) || 'siteRestrictedUser',
        authMethod: this.config.authType
      };
    } catch (err: any) {
      return {
        siteUrl,
        verified: false,
        permissionLevel: 'siteUnverified',
        authMethod: this.config.authType,
        errorMessage: err.message
      };
    }
  }
}
