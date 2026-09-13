/**
 * NovaPay Admin Panel Management Module
 */

let adminUsersList = [];
let selectedAdminUser = null;
let adminLogRows = [];
let adminLogPaused = false;
let adminDashboardTimer = null;
let adminMonitoringTimer = null;
let adminLogTimer = null;

document.addEventListener("DOMContentLoaded", () => {
    initAdminDashboard();
    initAdminUsersPage();
    initAdminMonitoringPage();
    initManualFailover();
    initLogStreamer();
});

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
        const message = payload?.error?.message || `Request failed: ${response.status}`;
        throw new Error(message);
    }
    return payload;
}

function adminNotify(message, type = "info") {
    if (typeof window.showToast === "function") {
        window.showToast(message, type);
    }
}

function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function clamp(value, min = 0, max = 100) {
    return Math.min(max, Math.max(min, Number(value) || 0));
}

function formatCurrency(value) {
    return new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "GBP"
    }).format(Number(value) || 0);
}

function formatNumber(value) {
    return new Intl.NumberFormat("en-GB").format(Number(value) || 0);
}

function formatDate(value) {
    if (!value) return "Not recorded";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not recorded";
    return new Intl.DateTimeFormat("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric"
    }).format(date);
}

function formatTime(value) {
    if (!value) return "00:00:00";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "00:00:00";
    return date.toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    });
}

function getInitials(name) {
    const parts = String(name || "User").trim().split(/\s+/).filter(Boolean);
    return (parts[0]?.[0] || "U") + (parts[1]?.[0] || parts[0]?.[1] || "");
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function setProgress(id, value) {
    const element = document.getElementById(id);
    if (element) element.style.width = `${clamp(value)}%`;
}

function setButtonLoading(button, loading, label) {
    if (!button) return;
    if (loading) {
        if (button.dataset.loading !== "true") {
            button.dataset.originalHtml = button.innerHTML;
        }
        button.dataset.loading = "true";
        button.disabled = true;
        button.textContent = label;
        return;
    }

    button.disabled = false;
    if (button.dataset.originalHtml) {
        button.innerHTML = button.dataset.originalHtml;
    }
    delete button.dataset.loading;
    delete button.dataset.originalHtml;
}

function animateMetric(element, target, formatter = formatNumber) {
    if (!element) return;

    const nextValue = Number(target) || 0;
    const startValue = Number(element.dataset.metricValue || 0);
    element.dataset.metricValue = String(nextValue);

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        element.textContent = formatter(nextValue);
        return;
    }

    const duration = 700;
    const start = performance.now();

    const tick = currentTime => {
        const progress = clamp((currentTime - start) / duration, 0, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const value = startValue + (nextValue - startValue) * eased;
        element.textContent = formatter(value);
        if (progress < 1) requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
}

function kycClass(status) {
    const clean = String(status || "pending").toLowerCase();
    if (["approved", "hold", "declined", "pending"].includes(clean)) return clean;
    return "pending";
}

function kycLabel(status) {
    const clean = kycClass(status);
    return clean.charAt(0).toUpperCase() + clean.slice(1);
}

function initAdminDashboard() {
    const statsContainer = document.getElementById("admin-stats-box");
    if (!statsContainer) return;

    const refreshButton = document.getElementById("admin-refresh-dashboard");
    const refreshActivityButton = document.getElementById("admin-refresh-activity");
    const insightBanner = document.getElementById("admin-insight-banner");

    statsContainer.querySelectorAll(".admin-kpi-card").forEach(card => {
        card.addEventListener("click", () => {
            statsContainer.querySelectorAll(".admin-kpi-card").forEach(item => item.classList.remove("active"));
            card.classList.add("active");
            if (insightBanner) insightBanner.textContent = card.dataset.adminInsight || "Metric selected.";
        });
    });

    const refresh = async (manual = false) => {
        setButtonLoading(refreshButton, manual, "Refreshing...");
        await Promise.allSettled([
            refreshAdminStats(),
            refreshDashboardUsers(),
            refreshMonitoringSnapshot(),
            refreshDashboardActivity()
        ]);
        setButtonLoading(refreshButton, false);
        if (manual) adminNotify("Admin command center refreshed.", "accent");
    };

    refreshButton?.addEventListener("click", () => refresh(true));
    refreshActivityButton?.addEventListener("click", () => refreshDashboardActivity(true));

    refresh();
    clearInterval(adminDashboardTimer);
    adminDashboardTimer = setInterval(refresh, 30000);
}

async function refreshAdminStats() {
    const response = await requestJson("/api/admin/stats");
    const data = response.data || {};

    animateMetric(document.getElementById("stat-users"), data.total_users, value => formatNumber(Math.round(value)));
    animateMetric(document.getElementById("stat-aum"), data.aum, formatCurrency);
    animateMetric(document.getElementById("stat-txns"), data.transaction_count, value => formatNumber(Math.round(value)));
    animateMetric(document.getElementById("stat-volume"), data.transaction_volume, formatCurrency);

    setText("stat-users-note", "Customer directory loaded");
    setText("stat-aum-note", "Assets under custody");
    setText("stat-txns-note", "Completed ledger events");
    setText("stat-volume-note", "Settled payment volume");
    setText("admin-action-ledger", `${formatNumber(data.transaction_count || 0)} txns`);

    setProgress("stat-users-progress", (Number(data.total_users) / 30) * 100);
    setProgress("stat-aum-progress", (Number(data.aum) / 100000) * 100);
    setProgress("stat-txns-progress", (Number(data.transaction_count) / 500) * 100);
    setProgress("stat-volume-progress", (Number(data.transaction_volume) / 150000) * 100);
}

async function refreshDashboardUsers() {
    const response = await requestJson("/api/admin/users");
    const users = response.data || [];
    const pending = users.filter(user => kycClass(user.kyc_status) === "pending").length;
    const approved = users.filter(user => kycClass(user.kyc_status) === "approved").length;
    const locked = users.filter(user => user.is_active === false).length;

    setText("admin-approved-users", approved);
    setText("admin-pending-users", pending);
    setText("admin-locked-users", locked);
    setText("admin-action-kyc-count", `${pending} pending`);

    const queue = users
        .filter(user => kycClass(user.kyc_status) !== "approved" || user.is_active === false)
        .concat(users.filter(user => kycClass(user.kyc_status) === "approved" && user.is_active !== false))
        .slice(0, 5);

    const list = document.getElementById("admin-user-triage-list");
    if (!list) return;

    if (!queue.length) {
        list.innerHTML = `<div class="admin-detail-empty">No customer records found.</div>`;
        return;
    }

    list.innerHTML = queue.map(user => `
        <a class="admin-triage-row" href="/admin/users?user=${encodeURIComponent(user.id)}">
            <span>
                <strong>${escapeHtml(user.full_name || "Unnamed customer")}</strong>
                <small>${escapeHtml(user.email || "No email")} · ${escapeHtml(formatDate(user.created_at))}</small>
            </span>
            <span class="admin-status-badge ${user.is_active === false ? "locked" : kycClass(user.kyc_status)}">
                ${user.is_active === false ? "Locked" : escapeHtml(kycLabel(user.kyc_status))}
            </span>
        </a>
    `).join("");
}

async function refreshDashboardActivity(manual = false) {
    const list = document.getElementById("admin-dashboard-log-list");
    if (!list) return;

    const [historyResponse, failoverResponse] = await Promise.allSettled([
        requestJson("/api/monitoring/history"),
        requestJson("/api/failover/history")
    ]);

    const logs = historyResponse.status === "fulfilled" ? (historyResponse.value.data || []) : [];
    const failovers = failoverResponse.status === "fulfilled" ? (failoverResponse.value.data || []) : [];

    const events = [
        ...failovers.slice(0, 3).map(event => ({
            type: "Failover",
            title: `${String(event.from_server || "node").toUpperCase()} to ${String(event.to_server || "node").toUpperCase()}`,
            meta: `${formatTime(event.triggered_at)} · RTO ${Number(event.rto_seconds || 0).toFixed(2)}s`
        })),
        ...logs.slice(0, 5).map(log => ({
            type: log.status === "UP" ? "Telemetry" : "Alert",
            title: `${String(log.server || "node").toUpperCase()} ${log.status || "UNKNOWN"}`,
            meta: `${formatTime(log.created_at)} · ${(Number(log.response_time || 0) * 1000).toFixed(0)}ms · CPU ${log.cpu_usage || 0}%`
        }))
    ].slice(0, 6);

    if (!events.length) {
        list.innerHTML = `<div class="admin-detail-empty">No telemetry events have been logged yet.</div>`;
    } else {
        list.innerHTML = events.map(event => `
            <div class="admin-event-row">
                <span>
                    <strong>${escapeHtml(event.title)}</strong>
                    <small>${escapeHtml(event.meta)}</small>
                </span>
                <span class="admin-status-badge ${event.type === "Alert" ? "declined" : "approved"}">${escapeHtml(event.type)}</span>
            </div>
        `).join("");
    }

    if (manual) adminNotify("Latest system activity refreshed.", "accent");
}

async function refreshMonitoringSnapshot() {
    const [healthResult, telemetryResult] = await Promise.allSettled([
        requestJson("/health"),
        requestJson("/api/monitoring/current")
    ]);

    if (healthResult.status === "fulfilled") {
        const health = healthResult.value || {};
        const server = String(health.server || "aws").toUpperCase();
        const summary = `DB ${String(health.db || "unknown").toUpperCase()} · ${Number(health.db_latency_ms || 0).toFixed(0)}ms database latency`;

        setText("admin-active-route", `${server} Active`);
        setText("monitor-active-route", `${server} Active`);
        setText("admin-health-summary", summary);
        setText("monitor-health-summary", summary);
        setText("admin-action-route", `${server} route`);
        setText("readiness-db", String(health.db || "unknown").toUpperCase());
        setText("readiness-route", `${server} Active`);
    }

    if (telemetryResult.status === "fulfilled") {
        const data = telemetryResult.value.data || {};
        updateNodeTelemetry("aws", data.aws);
        updateNodeTelemetry("azure", data.azure);
    }
}

function updateNodeTelemetry(node, data) {
    const label = node.toUpperCase();
    const status = String(data?.status || "UNKNOWN").toUpperCase();
    const latency = Number(data?.response_time || 0) * 1000;
    const cpu = Number(data?.cpu_usage || 0);
    const memory = Number(data?.memory_usage || 0);
    const score = status === "UP"
        ? clamp(100 - (latency / 20) - (cpu * 0.28) - (memory * 0.22), 0, 100)
        : 8;

    const statusClass = status === "UP" ? "green" : "red";
    const dashboardDot = document.getElementById(`dashboard-${node}-status`);
    const nodeDot = document.getElementById(`${node}-node-status`);

    if (dashboardDot) dashboardDot.className = `status-dot ${statusClass}`;
    if (nodeDot) nodeDot.className = `status-dot ${statusClass}`;

    setText(`dashboard-${node}-latency`, data ? `${latency.toFixed(0)}ms` : `${label} waiting`);
    setText(`${node}-latency`, data ? `${latency.toFixed(0)}ms` : "No sample");
    setText(`${node}-cpu`, `${cpu.toFixed(1)}%`);
    setText(`${node}-mem`, `${memory.toFixed(1)}%`);
    setText(`${node}-health-score`, Math.round(score));

    setProgress(`dashboard-${node}-meter`, score);
    setProgress(`${node}-cpu-bar`, cpu);
    setProgress(`${node}-mem-bar`, memory);

    const nodeScore = document.querySelector(`[data-node-card="${node}"] .admin-node-score`);
    if (nodeScore) nodeScore.style.setProperty("--node-score", `${score}%`);

    const note = document.getElementById("admin-cloud-note");
    if (note) note.textContent = `Latest samples: ${label} ${status} at ${latency.toFixed(0)}ms.`;
}

function initAdminUsersPage() {
    const tbody = document.getElementById("admin-users-tbody");
    if (!tbody) return;

    const searchInput = document.getElementById("admin-user-search");
    const kycFilter = document.getElementById("admin-kyc-filter");
    const statusFilter = document.getElementById("admin-status-filter");
    const refreshButton = document.getElementById("admin-users-refresh");
    const modal = document.getElementById("user-detail-modal");

    const render = () => renderUsersTable(filterUsers());

    searchInput?.addEventListener("input", render);
    kycFilter?.addEventListener("change", render);
    statusFilter?.addEventListener("change", render);
    refreshButton?.addEventListener("click", () => loadAdminUsers(true));

    document.querySelectorAll("[data-user-preset]").forEach(card => {
        card.addEventListener("click", () => {
            const preset = card.dataset.userPreset;
            if (searchInput) searchInput.value = "";
            if (kycFilter) kycFilter.value = ["pending", "approved"].includes(preset) ? preset : "all";
            if (statusFilter) statusFilter.value = preset === "locked" ? "locked" : "all";
            document.querySelectorAll("[data-user-preset]").forEach(item => item.classList.remove("active"));
            card.classList.add("active");
            render();
        });
    });

    document.getElementById("close-user-detail-modal")?.addEventListener("click", closeUserDetailModal);
    document.getElementById("btn-modal-close-secondary")?.addEventListener("click", closeUserDetailModal);
    modal?.addEventListener("click", event => {
        if (event.target === modal) closeUserDetailModal();
    });

    document.getElementById("btn-modal-freeze")?.addEventListener("click", toggleFreezeFromModal);
    document.querySelectorAll("[data-kyc-status]").forEach(button => {
        button.addEventListener("click", () => verifyKYCFromModal(button.dataset.kycStatus));
    });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && modal?.style.display === "flex") closeUserDetailModal();
    });

    loadAdminUsers();
}

async function loadAdminUsers(manual = false) {
    const tbody = document.getElementById("admin-users-tbody");
    const refreshButton = document.getElementById("admin-users-refresh");
    if (tbody && !adminUsersList.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="admin-empty-cell">Fetching customer directory...</td></tr>`;
    }

    setButtonLoading(refreshButton, manual, "Refreshing...");
    try {
        const response = await requestJson("/api/admin/users");
        adminUsersList = response.data || [];
        renderUsersSummary();
        renderUsersTable(filterUsers());
        await openUserFromQuery();
        if (manual) adminNotify("User directory refreshed.", "accent");
    } catch (error) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="admin-empty-cell">${escapeHtml(error.message)}</td></tr>`;
    } finally {
        setButtonLoading(refreshButton, false);
    }
}

function renderUsersSummary() {
    const total = adminUsersList.length;
    const pending = adminUsersList.filter(user => kycClass(user.kyc_status) === "pending").length;
    const locked = adminUsersList.filter(user => user.is_active === false).length;
    const approved = adminUsersList.filter(user => kycClass(user.kyc_status) === "approved").length;

    setText("users-total-count", total);
    setText("users-pending-count", pending);
    setText("users-locked-count", locked);
    setText("users-approved-count", approved);
}

function filterUsers() {
    const query = String(document.getElementById("admin-user-search")?.value || "").trim().toLowerCase();
    const kyc = document.getElementById("admin-kyc-filter")?.value || "all";
    const status = document.getElementById("admin-status-filter")?.value || "all";

    return adminUsersList.filter(user => {
        const haystack = [
            user.full_name,
            user.email,
            user.phone,
            user.id
        ].join(" ").toLowerCase();
        const queryMatch = !query || haystack.includes(query);
        const kycMatch = kyc === "all" || kycClass(user.kyc_status) === kyc;
        const statusMatch = status === "all"
            || (status === "active" && user.is_active !== false)
            || (status === "locked" && user.is_active === false);
        return queryMatch && kycMatch && statusMatch;
    });
}

function renderUsersTable(users) {
    const tbody = document.getElementById("admin-users-tbody");
    const resultCount = document.getElementById("admin-user-result-count");
    if (!tbody) return;

    if (resultCount) {
        resultCount.textContent = `${users.length} of ${adminUsersList.length} customers shown`;
    }

    if (!users.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="admin-empty-cell">No customers match the current filters.</td></tr>`;
        return;
    }

    tbody.innerHTML = users.map(user => {
        const isLocked = user.is_active === false;
        const kyc = kycClass(user.kyc_status);
        return `
            <tr>
                <td>
                    <button type="button" class="admin-user-identity" data-view-user="${escapeHtml(user.id)}">
                        <span class="admin-user-avatar">${escapeHtml(getInitials(user.full_name).toUpperCase())}</span>
                        <span>
                            <strong>${escapeHtml(user.full_name || "Unnamed customer")}</strong>
                            <small>ID ${escapeHtml(String(user.id || "").slice(0, 8))}</small>
                        </span>
                    </button>
                </td>
                <td>${escapeHtml(user.email || "No email")}</td>
                <td><span class="mono-code">${escapeHtml(user.phone || "Not set")}</span></td>
                <td><span class="admin-status-badge ${kyc}">${escapeHtml(kycLabel(kyc))}</span></td>
                <td><span class="admin-status-badge ${isLocked ? "locked" : "active"}">${isLocked ? "Locked" : "Active"}</span></td>
                <td><span class="admin-table-subtext">${escapeHtml(formatDate(user.created_at))}</span></td>
                <td class="admin-table-actions">
                    <div class="admin-row-actions">
                        <button type="button" class="btn btn-secondary" data-view-user="${escapeHtml(user.id)}">Audit Detail</button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");

    tbody.querySelectorAll("[data-view-user]").forEach(button => {
        button.addEventListener("click", () => viewUserDetail(button.dataset.viewUser));
    });
}

async function openUserFromQuery() {
    const userId = new URLSearchParams(window.location.search).get("user");
    if (!userId || selectedAdminUser?.user?.id === userId) return;
    if (!adminUsersList.some(user => String(user.id) === String(userId))) return;
    await viewUserDetail(userId);
}

async function viewUserDetail(id) {
    showUserModalLoading(id);
    try {
        const response = await requestJson(`/api/admin/users/${encodeURIComponent(id)}`);
        selectedAdminUser = response.data;
        renderUserDetail(response.data);
    } catch (error) {
        adminNotify(error.message || "Could not load user detail.", "error");
        closeUserDetailModal();
    }
}

function showUserModalLoading(id) {
    const modal = document.getElementById("user-detail-modal");
    if (!modal) return;

    selectedAdminUser = null;
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
    setText("user-modal-avatar", "--");
    setText("admin-user-modal-title", "Loading customer profile");
    setText("det-user-id", `ID ${id}`);
    setText("det-total-balance", formatCurrency(0));
    setText("det-account-count", "0");
    setText("det-product-status", "0 accounts");
    setText("det-fullname", "-");
    setText("det-email", "-");
    setText("det-phone", "-");
    setText("det-address", "-");
    setText("det-created", "-");
    setText("det-kyc", "LOADING");
    setText("det-active", "Loading");
    document.getElementById("det-accounts-box").innerHTML = `<div class="admin-detail-empty">Loading linked products...</div>`;
    setModalActionsDisabled(true);
    window.setTimeout(() => document.getElementById("close-user-detail-modal")?.focus(), 30);
}

function renderUserDetail(data) {
    const user = data.user || {};
    const accounts = data.accounts || [];
    const balanceTotal = accounts.reduce((sum, account) => sum + Number(account.balance || 0), 0);
    const address = [user.address, user.city, user.postcode].filter(Boolean).join(", ") || "Not recorded";
    const kyc = kycClass(user.kyc_status);
    const isLocked = user.is_active === false;

    setText("user-modal-avatar", getInitials(user.full_name).toUpperCase());
    setText("admin-user-modal-title", user.full_name || "Customer profile");
    setText("det-user-id", `ID ${String(user.id || "").slice(0, 12)}...`);
    setText("det-total-balance", formatCurrency(balanceTotal));
    setText("det-account-count", accounts.length);
    setText("det-product-status", `${accounts.length} account${accounts.length === 1 ? "" : "s"}`);
    setText("det-fullname", user.full_name || "Not recorded");
    setText("det-email", user.email || "Not recorded");
    setText("det-phone", user.phone || "Not recorded");
    setText("det-address", address);
    setText("det-created", formatDate(user.created_at));
    setText("det-kyc", kycLabel(kyc));
    setText("det-active", isLocked ? "Locked" : "Active");

    const kycBadge = document.getElementById("det-kyc");
    const activeBadge = document.getElementById("det-active");
    if (kycBadge) kycBadge.className = `admin-status-badge ${kyc}`;
    if (activeBadge) activeBadge.className = `admin-status-badge ${isLocked ? "locked" : "active"}`;

    const freezeButton = document.getElementById("btn-modal-freeze");
    if (freezeButton) freezeButton.textContent = isLocked ? "Unlock User Profile" : "Lock User Profile";

    renderUserDocument(user);
    renderUserAccounts(accounts);
    setModalActionsDisabled(false);
}

function renderUserDocument(user) {
    const docBox = document.getElementById("det-kyc-doc-section");
    const docImg = document.getElementById("det-doc-img");
    const docType = document.getElementById("det-doc-type");
    if (!docBox || !docImg || !docType) return;

    if (user.kyc_document_file) {
        docImg.src = user.kyc_document_file;
        docImg.alt = `${user.kyc_document_type || "KYC"} scan preview`;
        docType.textContent = user.kyc_document_type || "Document";
        docBox.classList.add("has-document");
    } else {
        docImg.removeAttribute("src");
        docImg.alt = "No KYC scan uploaded";
        docType.textContent = "No document";
        docBox.classList.remove("has-document");
    }
}

function renderUserAccounts(accounts) {
    const accountBox = document.getElementById("det-accounts-box");
    if (!accountBox) return;

    if (!accounts.length) {
        accountBox.innerHTML = `<div class="admin-detail-empty">No accounts are attached to this customer.</div>`;
        return;
    }

    accountBox.innerHTML = accounts.map(account => {
        const frozen = account.is_frozen === true;
        const inactive = account.is_active === false;
        const status = frozen ? "Frozen" : inactive ? "Inactive" : "Live";
        const statusClass = frozen ? "pending" : inactive ? "locked" : "active";
        return `
            <div class="admin-account-row">
                <span>
                    <strong>${escapeHtml(account.nickname || account.account_type || "Account")}</strong>
                    <small>${escapeHtml(account.account_number || "No account number")} · ${escapeHtml(account.sort_code || "No sort code")}</small>
                </span>
                <strong class="amount">${escapeHtml(formatCurrency(account.balance))}</strong>
                <span class="admin-status-badge ${statusClass}">${escapeHtml(status)}</span>
            </div>
        `;
    }).join("");
}

function setModalActionsDisabled(disabled) {
    document.querySelectorAll("#user-detail-modal button").forEach(button => {
        if (button.id !== "close-user-detail-modal" && button.id !== "btn-modal-close-secondary") {
            button.disabled = disabled;
        }
    });
}

function closeUserDetailModal() {
    const modal = document.getElementById("user-detail-modal");
    if (!modal) return;
    modal.style.display = "none";
    document.body.style.overflow = "";
    selectedAdminUser = null;
}

function verifyKYCFromModal(status) {
    if (!selectedAdminUser) return;
    const user = selectedAdminUser.user || {};
    const cleanStatus = kycClass(status);
    const actionButton = document.querySelector(`[data-kyc-status="${cleanStatus}"]`);
    const confirmed = window.confirm(`Update KYC for ${user.full_name || "this customer"} to ${cleanStatus.toUpperCase()}?`);
    if (!confirmed) return;

    setButtonLoading(actionButton, true, "Saving...");
    fetch(`/api/admin/users/${encodeURIComponent(user.id)}/verify-kyc`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken()
        },
        body: JSON.stringify({ status: cleanStatus })
    })
        .then(response => response.json())
        .then(response => {
            if (response.success) {
                adminNotify(`KYC updated to ${cleanStatus.toUpperCase()}.`, "accent");
                closeUserDetailModal();
                loadAdminUsers();
            } else {
                throw new Error(response?.error?.message || "Failed to update KYC status.");
            }
        })
        .catch(error => adminNotify(error.message || "Connection failed.", "error"))
        .finally(() => setButtonLoading(actionButton, false));
}

function toggleFreezeFromModal() {
    if (!selectedAdminUser) return;
    const user = selectedAdminUser.user || {};
    const willLock = user.is_active !== false;
    const confirmed = window.confirm(`${willLock ? "Lock" : "Unlock"} ${user.full_name || "this customer"}?`);
    if (!confirmed) return;

    const freezeButton = document.getElementById("btn-modal-freeze");
    setButtonLoading(freezeButton, true, willLock ? "Locking..." : "Unlocking...");

    fetch(`/api/admin/users/${encodeURIComponent(user.id)}/freeze`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfToken()
        }
    })
        .then(response => response.json())
        .then(response => {
            if (response.success) {
                adminNotify(`User profile ${response.data.is_active ? "unlocked" : "locked"}.`, "accent");
                closeUserDetailModal();
                loadAdminUsers();
            } else {
                throw new Error(response?.error?.message || "Failed to update user lock state.");
            }
        })
        .catch(error => adminNotify(error.message || "Connection failed.", "error"))
        .finally(() => setButtonLoading(freezeButton, false));
}

function initAdminMonitoringPage() {
    const page = document.querySelector(".admin-monitoring-page");
    if (!page) return;

    const refreshButton = document.getElementById("monitoring-refresh-btn");
    refreshButton?.addEventListener("click", async () => {
        setButtonLoading(refreshButton, true, "Checking...");
        await Promise.allSettled([
            refreshMonitoringSnapshot(),
            refreshFailoverHistory(),
            fetchAdminLogs()
        ]);
        setButtonLoading(refreshButton, false);
        adminNotify("System monitoring refreshed.", "accent");
    });

    page.querySelectorAll(".admin-readiness-item").forEach(item => {
        item.addEventListener("click", () => {
            item.classList.toggle("active");
            adminNotify("Readiness item toggled for this session.", "info");
        });
    });

    refreshMonitoringSnapshot();
    refreshFailoverHistory();
    clearInterval(adminMonitoringTimer);
    adminMonitoringTimer = setInterval(() => {
        refreshMonitoringSnapshot();
        refreshFailoverHistory();
    }, 10000);
}

function initManualFailover() {
    const failoverBtn = document.getElementById("trigger-failover-btn");
    const modal = document.getElementById("failover-modal");
    const confirmInput = document.getElementById("failover-confirm-input");
    const targetSelect = document.getElementById("failover-target-select");
    const submitBtn = document.getElementById("submit-failover-btn");
    const cancelBtn = document.getElementById("cancel-failover-btn");
    const closeBtn = document.getElementById("close-failover-modal");

    if (!failoverBtn || !modal || !submitBtn || !confirmInput || !targetSelect) return;

    const close = () => {
        modal.style.display = "none";
        document.body.style.overflow = "";
        confirmInput.value = "";
        submitBtn.disabled = true;
        submitBtn.textContent = "Trigger Failover";
    };

    failoverBtn.addEventListener("click", () => {
        modal.style.display = "flex";
        document.body.style.overflow = "hidden";
        confirmInput.value = "";
        submitBtn.disabled = true;
        window.setTimeout(() => targetSelect.focus(), 30);
    });

    cancelBtn?.addEventListener("click", close);
    closeBtn?.addEventListener("click", close);
    modal.addEventListener("click", event => {
        if (event.target === modal) close();
    });

    confirmInput.addEventListener("input", event => {
        submitBtn.disabled = event.target.value !== "FAILOVER";
    });

    submitBtn.addEventListener("click", () => {
        const target = targetSelect.value;
        setButtonLoading(submitBtn, true, "Processing...");

        fetch("/api/failover/manual", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken()
            },
            body: JSON.stringify({
                confirmation: "FAILOVER",
                target
            })
        })
            .then(response => response.json())
            .then(response => {
                if (response.success) {
                    adminNotify(`Failover to ${target.toUpperCase()} completed successfully.`, "accent");
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    throw new Error(response?.error?.message || "Manual failover failed.");
                }
            })
            .catch(error => {
                adminNotify(error.message || "Network error during manual failover.", "error");
                setButtonLoading(submitBtn, false);
                submitBtn.disabled = confirmInput.value !== "FAILOVER";
            });
    });
}

function initLogStreamer() {
    const logBox = document.getElementById("admin-log-stream");
    if (!logBox) return;

    const pauseButton = document.getElementById("log-pause-btn");
    const clearButton = document.getElementById("log-clear-btn");
    const filterSelect = document.getElementById("log-filter-select");

    pauseButton?.addEventListener("click", () => {
        adminLogPaused = !adminLogPaused;
        pauseButton.textContent = adminLogPaused ? "Resume" : "Pause";
        adminNotify(adminLogPaused ? "Telemetry stream paused." : "Telemetry stream resumed.", "info");
    });

    clearButton?.addEventListener("click", () => {
        logBox.innerHTML = `<div class="log-stream-entry">Log viewport cleared. Next refresh will reload telemetry.</div>`;
    });

    filterSelect?.addEventListener("change", renderLogStream);

    fetchAdminLogs();
    clearInterval(adminLogTimer);
    adminLogTimer = setInterval(() => {
        if (!adminLogPaused) fetchAdminLogs();
    }, 10000);
}

async function fetchAdminLogs() {
    const response = await requestJson("/api/monitoring/history");
    adminLogRows = response.data || [];
    renderLogStream();
}

function renderLogStream() {
    const logBox = document.getElementById("admin-log-stream");
    const filter = document.getElementById("log-filter-select")?.value || "all";
    if (!logBox) return;

    const logs = adminLogRows
        .filter(log => filter === "all" || String(log.server || "").toLowerCase() === filter)
        .slice(0, 60)
        .reverse();

    if (!logs.length) {
        logBox.innerHTML = `<div class="log-stream-entry">No telemetry samples for this filter.</div>`;
        return;
    }

    logBox.innerHTML = logs.map(log => {
        const status = String(log.status || "UNKNOWN").toUpperCase();
        const down = status !== "UP";
        const latency = (Number(log.response_time || 0) * 1000).toFixed(0);
        return `
            <div class="log-stream-entry ${down ? "status-down" : ""}">
                <span class="time">[${escapeHtml(formatTime(log.created_at))}]</span>
                <span class="server">${escapeHtml(String(log.server || "node").toUpperCase())}</span>:
                <span>${escapeHtml(status)}</span>
                <span>(Latency ${latency}ms | CPU ${escapeHtml(log.cpu_usage || 0)}% | MEM ${escapeHtml(log.memory_usage || 0)}%)</span>
            </div>
        `;
    }).join("");

    logBox.scrollTop = logBox.scrollHeight;
}

async function refreshFailoverHistory() {
    const list = document.getElementById("failover-history-list");
    if (!list) return;

    const response = await requestJson("/api/failover/history");
    const events = response.data || [];
    setText("failover-count-chip", `${events.length} event${events.length === 1 ? "" : "s"}`);

    if (!events.length) {
        list.innerHTML = `<div class="admin-detail-empty">No failover events recorded.</div>`;
        return;
    }

    list.innerHTML = events.slice(0, 8).map(event => `
        <div class="admin-event-row">
            <span>
                <strong>${escapeHtml(String(event.from_server || "node").toUpperCase())} to ${escapeHtml(String(event.to_server || "node").toUpperCase())}</strong>
                <small>${escapeHtml(formatDate(event.triggered_at))} · RTO ${Number(event.rto_seconds || 0).toFixed(2)}s</small>
            </span>
            <span class="admin-status-badge approved">Resolved</span>
        </div>
    `).join("");
}

window.closeUserDetailModal = closeUserDetailModal;
window.viewUserDetail = viewUserDetail;
window.verifyKYCFromModal = verifyKYCFromModal;
window.toggleFreezeFromModal = toggleFreezeFromModal;
