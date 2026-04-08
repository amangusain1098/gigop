const loginForm = document.getElementById("login-form");
const loginStatus = document.getElementById("login-status");

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginStatus.textContent = "Signing in...";
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("login-username").value,
        password: document.getElementById("login-password").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      loginStatus.textContent = payload.detail || "Sign-in failed.";
      return;
    }
    window.location.href = "/";
  });
}
