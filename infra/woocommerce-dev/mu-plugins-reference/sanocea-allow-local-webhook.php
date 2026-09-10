<?php
/**
 * LOCAL TEST ENVIRONMENT ONLY - not part of Sanocea's codebase, not deployed anywhere, not a
 * WooCommerce or Sanocea code change. Copy into the wp-env WordPress container's
 * wp-content/mu-plugins/ directory (auto-loads, no activation needed) when standing up this
 * environment fresh - see docs/architecture/woocommerce-platform-independence.md.
 *
 * WHY THIS EXISTS: WordPress's wp_http_validate_url() (used by wp_safe_remote_post(), which
 * WooCommerce's webhook delivery calls) rejects any destination host that resolves to a private/
 * loopback IP range as a built-in SSRF protection - and Docker Desktop's host.docker.internal
 * gateway address falls in that range. A REAL production WooCommerce store's webhook target (a real
 * public/routable HTTPS Sanocea endpoint) would never trigger this check at all; this filter exists
 * purely so THIS local Docker-container-to-Windows-host webhook delivery path works during testing.
 */

add_filter('http_request_host_is_external', function ($is_external, $host, $url) {
    if ($host === 'host.docker.internal') {
        return true;
    }
    return $is_external;
}, 10, 3);
