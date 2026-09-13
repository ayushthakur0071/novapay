/**
 * NovaPay Main Global JavaScript Controller
 */

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initCommandPalette();
    initSessionTimeout();
    initNotificationPoll();
    initMobileNav();
});

/* --------------------------------------------------------------------------
   Theme Switcher (Persisted Dark Mode)
-------------------------------------------------------------------------- */
function initTheme() {
    const themeToggle = document.getElementById("theme-toggle");
    const currentTheme = localStorage.getItem("theme") || "light";
    
    document.documentElement.setAttribute("data-theme", currentTheme);
    if (themeToggle) {
        themeToggle.checked = (currentTheme === "dark");
        themeToggle.addEventListener("change", (e) => {
            const nextTheme = e.target.checked ? "dark" : "light";
            document.documentElement.setAttribute("data-theme", nextTheme);
            localStorage.setItem("theme", nextTheme);
            showToast(`Theme changed to ${nextTheme} mode`, "info");
        });
    }
}

/* --------------------------------------------------------------------------
   Toast Alerts Engine
-------------------------------------------------------------------------- */
function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.classList.add("toast-container");
        document.body.appendChild(container);
    }
    
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        toast.classList.add("hiding");
        toast.addEventListener("animationend", () => {
            toast.remove();
        });
    }, 4000);
}
window.showToast = showToast;

/* --------------------------------------------------------------------------
   Global Search Command Palette (Ctrl+K)
-------------------------------------------------------------------------- */
function initCommandPalette() {
    const paletteBackdrop = document.getElementById("cmd-palette-backdrop");
    const cmdInput = document.getElementById("cmd-search-input");
    const resultsContainer = document.getElementById("cmd-results");
    const cmdTrigger = document.getElementById("cmd-trigger");
    
    if (!paletteBackdrop || !cmdInput) return;
    
    // Show palette on click of the header search box
    if (cmdTrigger) {
        cmdTrigger.addEventListener("click", () => {
            paletteBackdrop.style.display = "flex";
            cmdInput.focus();
        });
    }
    
    // Show palette on Ctrl+K
    window.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "k") {
            e.preventDefault();
            paletteBackdrop.style.display = "flex";
            cmdInput.focus();
        }
        if (e.key === "Escape") {
            closePalette();
        }
    });

    paletteBackdrop.addEventListener("click", (e) => {
        if (e.target === paletteBackdrop) {
            closePalette();
        }
    });

    cmdInput.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase().trim();
        searchPalette(query);
    });
    
    function closePalette() {
        paletteBackdrop.style.display = "none";
        cmdInput.value = "";
        if (resultsContainer) resultsContainer.innerHTML = "";
    }
    
    function searchPalette(query) {
        if (!resultsContainer) return;
        if (!query) {
            resultsContainer.innerHTML = "";
            return;
        }
        
        // Navigation options
        const navItems = [
            { title: "Go to Dashboard", url: "/dashboard", cat: "navigation" },
            { title: "Go to Transfer Funds", url: "/transactions/transfer", cat: "navigation" },
            { title: "View Card Limits", url: "/cards", cat: "navigation" },
            { title: "Open Support Tickets", url: "/support", cat: "navigation" },
            { title: "System Settings", url: "/settings", cat: "navigation" },
            { title: "Logout", url: "/logout", cat: "system" }
        ];
        
        const filteredNav = navItems.filter(i => i.title.toLowerCase().includes(query));
        
        // Query matching transactions
        fetch(`/api/transactions?search=${encodeURIComponent(query)}`)
        .then(r => r.json())
        .then(res => {
            let matches = [...filteredNav];
            if (res.success && res.data) {
                res.data.forEach(t => {
                    const direction = t.amount < 0 || t.from_account_number ? "Debit" : "Credit";
                    matches.push({
                        title: `${t.description || t.reference || 'Transaction'} - £${Math.abs(t.amount).toFixed(2)} (${t.category})`,
                        url: `/transactions/history`,
                        cat: `transaction (${direction})`
                    });
                });
            }
            renderResults(matches, query);
        })
        .catch(() => {
            renderResults(filteredNav, query);
        });
    }

    function renderResults(filtered, query) {
        if (filtered.length === 0) {
            resultsContainer.innerHTML = `<div class="cmd-item">No results found for "${query}"</div>`;
            return;
        }
        
        resultsContainer.innerHTML = filtered.map((item, idx) => `
            <div class="cmd-item" data-url="${item.url}">
                <div style="display:flex; flex-direction:column;">
                    <span style="font-weight:600; color:var(--text-primary);">${item.title}</span>
                    <span style="font-size:11px; color:var(--text-muted); text-transform:uppercase;">${item.cat}</span>
                </div>
            </div>
        `).join("");
        
        // Add navigation click
        document.querySelectorAll(".cmd-item").forEach(item => {
            item.addEventListener("click", () => {
                const url = item.dataset.url;
                if (url) window.location.href = url;
            });
        });
    }
}

/* --------------------------------------------------------------------------
   Session Expiry Security Daemon (55/59 Warning)
-------------------------------------------------------------------------- */
function initSessionTimeout() {
    // Session expires in 60 min. Warning at 55 min, modal at 59 min.
    const warningTime = 55 * 60 * 1000;
    const alertTime = 59 * 60 * 1000;
    
    let warnTimer = setTimeout(showTimeoutBanner, warningTime);
    let modalTimer = setTimeout(showTimeoutModal, alertTime);
    
    // Reset timers on mouse/keyboard movements (keepalive session simulation)
    function resetTimers() {
        clearTimeout(warnTimer);
        clearTimeout(modalTimer);
        
        warnTimer = setTimeout(showTimeoutBanner, warningTime);
        modalTimer = setTimeout(showTimeoutModal, alertTime);
        
        // Hide timeout banner if active
        const banner = document.getElementById("timeout-banner");
        if (banner) banner.style.display = "none";
    }
    
    window.addEventListener("mousemove", throttle(resetTimers, 10000));
    window.addEventListener("keydown", throttle(resetTimers, 10000));
}

function showTimeoutBanner() {
    let banner = document.getElementById("timeout-banner");
    if (!banner) {
        banner = document.createElement("div");
        banner.id = "timeout-banner";
        banner.style.cssText = "position:fixed; top:70px; left:0; width:100%; padding:10px; background-color:var(--accent-warm); color:var(--primary); font-weight:600; font-size:13px; text-align:center; z-index:999; box-shadow:0 2px 5px rgba(0,0,0,0.1);";
        banner.innerHTML = `⚠️ Your banking session will expire in 5 minutes due to inactivity. Move your mouse or type to continue.`;
        document.body.appendChild(banner);
    }
    banner.style.display = "block";
}

function showTimeoutModal() {
    let overlay = document.getElementById("timeout-modal");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "timeout-modal";
        overlay.classList.add("cmd-palette-backdrop");
        overlay.innerHTML = `
            <div class="cmd-palette" style="padding:24px; text-align:center;">
                <h3 style="margin-bottom:12px; font-size:18px; font-weight:700;">Security Timeout Warning</h3>
                <p style="margin-bottom:20px; color:var(--text-secondary);">Your banking session is about to close for security. You will be logged out in <span id="timeout-sec" style="font-weight:700; color:var(--danger);">60</span> seconds.</p>
                <button id="timeout-btn" class="btn btn-primary">Keep Me Logged In</button>
            </div>
        `;
        document.body.appendChild(overlay);
        
        document.getElementById("timeout-btn").addEventListener("click", () => {
            overlay.style.display = "none";
            // trigger keepalive ping request to server
            fetch("/api/auth/me").catch(() => {});
        });
    }
    overlay.style.display = "flex";
    
    let secLeft = 60;
    const counterEl = document.getElementById("timeout-sec");
    const interval = setInterval(() => {
        secLeft--;
        if (counterEl) counterEl.textContent = secLeft;
        
        if (secLeft <= 0) {
            clearInterval(interval);
            window.location.href = "/logout";
        }
    }, 1000);
}

/* --------------------------------------------------------------------------
   Unread notifications polling (every 60 seconds)
-------------------------------------------------------------------------- */
function initNotificationPoll() {
    const updateBadge = () => {
        fetch("/api/notifications")
            .then(r => r.json())
            .then(res => {
                if (res.success && res.data) {
                    const unread = res.data.filter(n => !n.is_read).length;
                    const badge = document.querySelector(".notif-badge");
                    if (badge) {
                        if (unread > 0) {
                            badge.textContent = unread;
                            badge.style.display = "flex";
                        } else {
                            badge.style.display = "none";
                        }
                    }
                }
            })
            .catch(() => {});
    };
    
    // Initial fetch and poll
    updateBadge();
    setInterval(updateBadge, 60000);
}

/* --------------------------------------------------------------------------
   Mobile side drawer drawer
-------------------------------------------------------------------------- */
function initMobileNav() {
    const hamburger = document.getElementById("hamburger-btn");
    const sidebar = document.querySelector(".sidebar");
    
    if (hamburger && sidebar) {
        hamburger.addEventListener("click", () => {
            sidebar.classList.toggle("open");
        });
    }
}

// Throttle utility
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    }
}
