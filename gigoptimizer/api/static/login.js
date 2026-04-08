const loginForm = document.getElementById("login-form");
const loginStatus = document.getElementById("login-status");
const submitButton = loginForm ? loginForm.querySelector('button[type="submit"]') : null;
const consentBanner = document.getElementById("cookie-consent-banner");
const acceptConsentButton = document.getElementById("cookie-consent-accept");
const declineConsentButton = document.getElementById("cookie-consent-decline");
const LOGIN_CLIENT_KEY = "gigoptimizer-login-client-id";
const COOKIE_CONSENT_KEY = "gigoptimizer-cookie-consent";
const CAMERA_PERMISSION_KEY = "gigoptimizer-camera-permission";

function ensureClientId() {
  const existing = window.localStorage.getItem(LOGIN_CLIENT_KEY);
  if (existing) {
    return existing;
  }
  const generated = typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `gigoptimizer-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(LOGIN_CLIENT_KEY, generated);
  return generated;
}

function getCookieConsent() {
  return window.localStorage.getItem(COOKIE_CONSENT_KEY) || "";
}

function setCookieConsent(value) {
  window.localStorage.setItem(COOKIE_CONSENT_KEY, value);
  if (consentBanner) {
    consentBanner.hidden = true;
  }
}

function setCameraPermission(value) {
  window.localStorage.setItem(CAMERA_PERMISSION_KEY, value);
}

function getCameraPermission() {
  return window.localStorage.getItem(CAMERA_PERMISSION_KEY) || "";
}

async function requestCameraAccessPreview() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setCameraPermission("unsupported");
    return "Camera access is not available in this browser.";
  }
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user" },
      audio: false,
    });
    setCameraPermission("granted");
    return "Cookie and camera permission accepted.";
  } catch (error) {
    setCameraPermission("denied");
    return "Cookie consent was accepted, but camera permission was denied.";
  } finally {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
  }
}

async function ensureCameraPermissionOnVisit() {
  if (getCookieConsent() !== "accepted") {
    return;
  }
  if (getCameraPermission() === "granted" || getCameraPermission() === "unsupported") {
    return;
  }
  if (loginStatus) {
    loginStatus.textContent = "Requesting camera permission...";
  }
  const detail = await requestCameraAccessPreview();
  if (loginStatus) {
    loginStatus.textContent = detail;
  }
}

function initializeConsentBanner() {
  if (!consentBanner) {
    return;
  }
  const consent = getCookieConsent();
  consentBanner.hidden = Boolean(consent);
  if (acceptConsentButton) {
    acceptConsentButton.addEventListener("click", async () => {
      setCookieConsent("accepted");
      if (loginStatus) {
        loginStatus.textContent = "Requesting camera permission...";
      }
      const detail = await requestCameraAccessPreview();
      if (loginStatus) {
        loginStatus.textContent = detail;
      }
    });
  }
  if (consent === "accepted") {
    void ensureCameraPermissionOnVisit();
  }
  if (declineConsentButton) {
    declineConsentButton.addEventListener("click", () => {
      setCookieConsent("declined");
      setCameraPermission("declined");
      if (loginStatus) {
        loginStatus.textContent = "Cookie consent declined. Standard sign-in remains available.";
      }
    });
  }
}

function collectDeviceInfo() {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  return {
    platform: navigator.platform || "",
    language: navigator.language || "",
    screen: window.screen ? `${window.screen.width}x${window.screen.height}` : "",
    timezone,
    touch_points: typeof navigator.maxTouchPoints === "number" ? String(navigator.maxTouchPoints) : "",
  };
}

async function postCapture(payload) {
  const response = await fetch("/api/auth/login-attempts/capture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Unable to store the security capture.");
  }
  return response.json();
}

async function captureFailurePhoto(attemptId, clientId) {
  if (getCookieConsent() !== "accepted") {
    await postCapture({
      attempt_id: attemptId,
      client_id: clientId,
      capture_error: "consent_declined",
      device_info: collectDeviceInfo(),
    });
    return "Additional security verification could not continue because consent was not granted.";
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    await postCapture({
      attempt_id: attemptId,
      client_id: clientId,
      capture_error: "camera_not_supported",
      device_info: collectDeviceInfo(),
    });
    return "Camera permission is required, but this browser does not support camera access.";
  }

  let stream = null;
  const video = document.createElement("video");
  video.setAttribute("playsinline", "true");
  video.muted = true;
  video.style.position = "fixed";
  video.style.left = "-9999px";
  video.style.top = "-9999px";
  document.body.appendChild(video);

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    await new Promise((resolve) => window.setTimeout(resolve, 400));

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("camera_context_unavailable");
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.88);
    const imageBase64 = dataUrl.split(",")[1] || "";
    await postCapture({
      attempt_id: attemptId,
      client_id: clientId,
      content_type: "image/jpeg",
      image_base64: imageBase64,
      device_info: collectDeviceInfo(),
    });
    return "Additional security verification completed.";
  } catch (error) {
    const message = error instanceof Error ? error.message : "camera_denied";
    setCameraPermission("denied");
    await postCapture({
      attempt_id: attemptId,
      client_id: clientId,
      capture_error: message,
      device_info: collectDeviceInfo(),
    });
    return "Camera permission is required to complete the additional security check.";
  } finally {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    video.remove();
  }
}

initializeConsentBanner();

if (loginForm && loginStatus) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const clientId = ensureClientId();
    loginStatus.textContent = "Signing in...";
    if (submitButton) {
      submitButton.disabled = true;
    }

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("login-username").value,
          password: document.getElementById("login-password").value,
          client_id: clientId,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        let message = payload.detail || "Sign-in failed.";
        if (payload.capture_required && payload.attempt_id) {
          loginStatus.textContent = "Additional security verification required...";
          try {
            const captureMessage = await captureFailurePhoto(payload.attempt_id, clientId);
            message = `${message} ${captureMessage}`;
          } catch (captureError) {
            const captureDetail = captureError instanceof Error ? captureError.message : "Unable to store the security capture.";
            message = `${message} ${captureDetail}`;
          }
        } else if (payload.failed_attempts) {
          message = `${message} Failed attempts: ${payload.failed_attempts}.`;
        }
        loginStatus.textContent = message;
        return;
      }
      window.location.href = "/";
    } catch (error) {
      loginStatus.textContent = error instanceof Error ? error.message : "Sign-in failed.";
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
      }
    }
  });
}
