import { Router, type Request, type Response, type Router as RouterType } from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';
import { getWorkspaceHostname } from '@chat-template/ai-sdk-providers';

export const dashboardRouter: RouterType = Router();

dashboardRouter.use(authMiddleware);

interface TokenInfo {
  authorization_details: unknown;
  [key: string]: unknown;
}

interface UserContext {
  externalViewerId: string; // unique user identifier for access auditing
  externalValue: string;    // user attribute for row-level security filtering
}

async function mintDashboardToken(user: UserContext): Promise<string> {
  const workspaceUrl = await getWorkspaceHostname();
  const spClientId = process.env.DATABRICKS_CLIENT_ID || process.env.DASHBOARD_SERVICE_PRINCIPAL_ID;
  const spToken = process.env.DATABRICKS_CLIENT_SECRET ||  process.env.DASHBOARD_SERVICE_PRINCIPAL_TOKEN;
  const dashboardId = process.env.DATABRICKS_DASHBOARD_ID;

  if (!workspaceUrl || !spClientId || !spToken || !dashboardId) {
    throw new Error(
      'Missing required env vars: DATABRICKS_HOST, (DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET) or (DASHBOARD_SERVICE_PRINCIPAL_ID, DASHBOARD_SERVICE_PRINCIPAL_TOKEN), DATABRICKS_DASHBOARD_ID',
    );
  }

  const basicAuth = Buffer.from(`${spClientId}:${spToken}`).toString('base64');

  // Step 1: Get all-apis OIDC token via client_credentials
  const oidcRes = await fetch(`${workspaceUrl}/oidc/v1/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${basicAuth}`,
    },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      scope: 'all-apis',
    }),
  });

  if (!oidcRes.ok) {
    throw new Error(`OIDC step 1 failed: ${oidcRes.status} ${await oidcRes.text()}`);
  }

  const { access_token: oidcToken } = (await oidcRes.json()) as {
    access_token: string;
  };

  // Step 2: Get token info with user context for RLS (external_value) and auditing (external_viewer_id)
  const tokenInfoUrl = new URL(
    `${workspaceUrl}/api/2.0/lakeview/dashboards/${dashboardId}/published/tokeninfo`,
  );
  tokenInfoUrl.searchParams.set('external_viewer_id', user.externalViewerId);
  tokenInfoUrl.searchParams.set('external_value', user.externalValue);

  const tokenInfoRes = await fetch(tokenInfoUrl.toString(), {
    headers: { Authorization: `Bearer ${oidcToken}` },
  });

  if (!tokenInfoRes.ok) {
    throw new Error(
      `Token info step 2 failed: ${tokenInfoRes.status} ${await tokenInfoRes.text()}`,
    );
  }

  const tokenInfo = (await tokenInfoRes.json()) as TokenInfo;

  // Step 3: Exchange for scoped token with authorization_details from step 2
  const { authorization_details, ...rest } = tokenInfo;

  const scopedParams = new URLSearchParams();
  for (const [k, v] of Object.entries(rest)) {
    if (v !== undefined && v !== null) {
      scopedParams.set(k, String(v));
    }
  }
  scopedParams.set('grant_type', 'client_credentials');
  scopedParams.set('authorization_details', JSON.stringify(authorization_details));
  // dashboard_id must be an explicit top-level JWT claim; /published/embedded checks it
  // directly and does not inspect authorization_details for it.
  scopedParams.set('dashboard_id', dashboardId);

  const scopedRes = await fetch(`${workspaceUrl}/oidc/v1/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${basicAuth}`,
    },
    body: scopedParams,
  });

  if (!scopedRes.ok) {
    throw new Error(`Scoped token step 3 failed: ${scopedRes.status} ${await scopedRes.text()}`);
  }

  const { access_token } = (await scopedRes.json()) as { access_token: string };
  return access_token;
}

dashboardRouter.get('/embed-config', requireAuth, async (req: Request, res: Response) => {
  try {
    const userEmail = req.session?.user.email ?? '';
    const embedToken = await mintDashboardToken({
      externalViewerId: userEmail,
      externalValue: userEmail,
    });

    const workspaceUrl = await getWorkspaceHostname();

    if (!workspaceUrl) {
      throw new Error('Failed to determine workspace URL');
    }

    res.json({
      workspace_url: workspaceUrl,
      dashboard_id: process.env.DATABRICKS_DASHBOARD_ID ?? '',
      embed_token: embedToken,
    });
  } catch (err) {
    console.error('[dashboard] Token minting failed:', err);
    res.status(502).json({
      error: 'Failed to generate dashboard embed token',
      message: err instanceof Error ? err.message : String(err),
    });
  }
});
