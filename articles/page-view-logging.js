(function () {
  "use strict";

  var endpoint = (window.AGENT_SYSTEMS_LOGGING_ENDPOINT || "").trim();
  if (!endpoint || window.__agentSystemsStaticPageViewLogged) {
    return;
  }
  window.__agentSystemsStaticPageViewLogged = true;

  function createVisitId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
      }
    } catch (_error) {
      // Fall through to the timestamp-based id below.
    }
    return "visit-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  function sessionValue(key) {
    try {
      return window.sessionStorage.getItem(key) || "";
    } catch (_error) {
      return "";
    }
  }

  function rememberSessionValue(key, value) {
    try {
      window.sessionStorage.setItem(key, value);
    } catch (_error) {
      // Logging should never interrupt reading the article.
    }
  }

  function visitId() {
    var key = "agent-systems-static-visit-id";
    var existing = sessionValue(key);
    if (existing) {
      return existing;
    }
    var created = createVisitId();
    rememberSessionValue(key, created);
    return created;
  }

  function visitAttribution() {
    var currentUrl = new URL(window.location.href);
    var source = currentUrl.searchParams.get("source") || currentUrl.searchParams.get("utm_source") || "";
    var entry = currentUrl.searchParams.get("entry") || "";
    if (source || entry) {
      rememberSessionValue("agent-systems-visit-source", source);
      rememberSessionValue("agent-systems-entry-path", entry);
    }
    return {
      visit_source: source || sessionValue("agent-systems-visit-source"),
      entry_path: entry || sessionValue("agent-systems-entry-path"),
    };
  }

  function stringify(value) {
    return value === undefined || value === null ? "" : String(value);
  }

  function countryHint(locale) {
    try {
      return new Intl.Locale(locale).region || "";
    } catch (_error) {
      var parts = String(locale || "").split("-");
      return parts.length > 1 ? parts[parts.length - 1] : "";
    }
  }

  function browserContext() {
    var timezone = "";
    try {
      timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (_error) {
      timezone = "";
    }
    var timezoneParts = timezone.split("/");
    var locale = navigator.language || "";
    var connection = navigator.connection || {};

    return {
      timezone: timezone,
      timezone_area: timezoneParts[0] || "",
      timezone_city: timezoneParts.slice(1).join("/").replace(/_/g, " "),
      locale: locale,
      country_hint: countryHint(locale),
      languages: Array.from(navigator.languages || []),
      user_agent: navigator.userAgent || "",
      platform: navigator.platform || "",
      vendor: navigator.vendor || "",
      app_name: navigator.appName || "",
      app_code_name: navigator.appCodeName || "",
      app_version: navigator.appVersion || "",
      product: navigator.product || "",
      product_sub: navigator.productSub || "",
      cookie_enabled: navigator.cookieEnabled,
      do_not_track: navigator.doNotTrack || "",
      hardware_concurrency: stringify(navigator.hardwareConcurrency),
      device_memory: stringify(navigator.deviceMemory),
      max_touch_points: stringify(navigator.maxTouchPoints),
      pdf_viewer_enabled: navigator.pdfViewerEnabled || "",
      webdriver: navigator.webdriver,
      online: navigator.onLine,
      screen: window.screen ? window.screen.width + "x" + window.screen.height : "",
      screen_details: {
        width: stringify(window.screen && window.screen.width),
        height: stringify(window.screen && window.screen.height),
        avail_width: stringify(window.screen && window.screen.availWidth),
        avail_height: stringify(window.screen && window.screen.availHeight),
        color_depth: stringify(window.screen && window.screen.colorDepth),
        pixel_depth: stringify(window.screen && window.screen.pixelDepth),
      },
      viewport: window.innerWidth + "x" + window.innerHeight,
      window_details: {
        inner_width: stringify(window.innerWidth),
        inner_height: stringify(window.innerHeight),
        outer_width: stringify(window.outerWidth),
        outer_height: stringify(window.outerHeight),
      },
      connection: {
        effective_type: connection.effectiveType || "",
        downlink: stringify(connection.downlink),
        rtt: stringify(connection.rtt),
        save_data: connection.saveData || false,
      },
      device_pixel_ratio: stringify(window.devicePixelRatio),
      referrer: document.referrer || "",
    };
  }

  function encodePayload(payload) {
    return window.btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
  }

  function logPageView() {
    var attribution = visitAttribution();
    var payload = {
      visit_id: visitId(),
      page_link: window.location.href,
      route: window.location.pathname + window.location.search + window.location.hash,
      page_title: document.title || "",
      timestamp: new Date().toISOString(),
      site: "custom-agent-tools-and-runtime",
      visit_source: attribution.visit_source,
      entry_path: attribution.entry_path,
      browser: browserContext(),
    };

    window.fetch(endpoint, {
      method: "POST",
      mode: "cors",
      keepalive: true,
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ param: encodePayload(payload) }),
    }).catch(function () {
      // Visit logging should never interrupt reading the article.
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", logPageView, { once: true });
  } else {
    logPageView();
  }
})();
