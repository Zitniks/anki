// Login / Register page

// Check if already logged in
(async () => {
    try {
        const res = await fetch('/api/v1/auth/me', { credentials: 'same-origin' });
        if (res.ok) window.location.href = '/';
    } catch {
        // not logged in, stay on login page
    }
})();

// ========== THEME ==========

function initTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
}

// ========== STATE ==========

let isRegisterMode = false;

// ========== DOM HELPERS ==========

function setMode(register) {
    isRegisterMode = register;
    document.getElementById('loginTitle').textContent = register ? 'Create account' : 'Welcome back';
    document.getElementById('loginSubtitle').textContent = register ? 'Register a new account' : 'Sign in to your account';
    document.getElementById('submitBtn').textContent = register ? 'Register' : 'Sign in';
    document.getElementById('toggleText').textContent = register ? 'Already have an account?' : "Don't have an account?";
    document.getElementById('toggleLink').textContent = register ? 'Sign in' : 'Register';
    document.getElementById('passwordInput').autocomplete = register ? 'new-password' : 'current-password';
    document.getElementById('loginError').style.display = 'none';
}

function toggleMode() {
    setMode(!isRegisterMode);
}

function showError(msg) {
    const el = document.getElementById('loginError');
    el.textContent = msg;
    el.style.display = 'block';
}

// ========== SUBMIT ==========

async function handleSubmit(e) {
    e.preventDefault();
    const email = document.getElementById('emailInput').value.trim();
    const password = document.getElementById('passwordInput').value;
    const btn = document.getElementById('submitBtn');

    document.getElementById('loginError').style.display = 'none';
    btn.disabled = true;
    btn.textContent = isRegisterMode ? 'Registering…' : 'Signing in…';

    const endpoint = isRegisterMode ? '/api/v1/auth/register' : '/api/v1/auth/login';
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await res.json();
        if (!res.ok) {
            showError(data.detail || 'Something went wrong');
            return;
        }
        window.location.href = '/';
    } catch {
        showError('Network error — please try again');
    } finally {
        btn.disabled = false;
        btn.textContent = isRegisterMode ? 'Register' : 'Sign in';
    }
}

// ========== INIT ==========

initTheme();

// Hide register option if registration is disabled
(async () => {
    try {
        const res = await fetch('/api/v1/auth/registration-enabled');
        const data = await res.json();
        if (!data.enabled) {
            const toggleText = document.getElementById('toggleText');
            const toggleLink = document.getElementById('toggleLink');
            if (toggleText) toggleText.style.display = 'none';
            if (toggleLink) toggleLink.style.display = 'none';
        }
    } catch {
        // If check fails, keep UI as-is
    }
})();
