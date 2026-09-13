const BACKEND_ORIGIN = "https://novapay-backend-cc5i.onrender.com";

export default {
  async fetch(request) {
    const incomingUrl = new URL(request.url);
    const backendUrl = new URL(
      incomingUrl.pathname + incomingUrl.search,
      BACKEND_ORIGIN
    );

    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.set("X-Forwarded-Host", incomingUrl.host);
    headers.set("X-Forwarded-Proto", "https");

    const clientIp = request.headers.get("CF-Connecting-IP");
    if (clientIp) {
      headers.set("X-Forwarded-For", clientIp);
      headers.set("X-Real-IP", clientIp);
    }

    const init = {
      method: request.method,
      headers,
      redirect: "manual"
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    const response = await fetch(new Request(backendUrl, init));
    const responseHeaders = new Headers(response.headers);
    const location = responseHeaders.get("Location");

    if (location) {
      try {
        const rewritten = new URL(location, BACKEND_ORIGIN);
        if (rewritten.origin === BACKEND_ORIGIN) {
          rewritten.protocol = incomingUrl.protocol;
          rewritten.host = incomingUrl.host;
          responseHeaders.set("Location", rewritten.toString());
        }
      } catch {
        // Relative redirects are already correct for the Cloudflare URL.
      }
    }

    responseHeaders.set("X-NovaPay-Frontend", "cloudflare-workers");

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders
    });
  }
};
