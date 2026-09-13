/**
 * NovaPay Customer Dashboard UI Module
 */

document.addEventListener("DOMContentLoaded", () => {
    initDashboardCounters();
    initDashboardGreeting();
    initSpendingAnalytics();
    initDashboardAccountDetails();
    initDashboardSafetyCenter();
    initDashboardForms();
    initOnboardingChecklist();
});

function getDashboardConfig() {
    return window.NovaPayDashboard || {};
}

function formatCurrency(value) {
    const amount = Number.parseFloat(value || 0);
    return new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "GBP"
    }).format(Number.isFinite(amount) ? amount : 0);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function titleCase(value) {
    return String(value || "")
        .replace(/_/g, " ")
        .split(/\s+/)
        .filter(Boolean)
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(" ");
}

function formatDate(value) {
    if (!value) return "Not available";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value).split("T")[0] || "Not available";
    }
    return new Intl.DateTimeFormat("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric"
    }).format(date);
}

function setElementText(id, text) {
    const element = document.getElementById(id);
    if (element) element.textContent = text;
}

function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
}

function notify(message, type = "info") {
    if (typeof window.showToast === "function") {
        window.showToast(message, type);
    }
}

function setButtonLoading(button, isLoading, loadingText = "Saving...") {
    if (!button) return;
    if (!button.dataset.defaultText) {
        button.dataset.defaultText = button.textContent.trim();
    }
    button.disabled = isLoading;
    button.textContent = isLoading ? loadingText : button.dataset.defaultText;
}

function reloadSoon(delay = 800) {
    window.setTimeout(() => window.location.reload(), delay);
}

function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.style.display = "flex";
    const firstField = modal.querySelector("input:not([type='hidden']), select, button");
    if (firstField) firstField.focus();
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.style.display = "none";
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": getCsrfToken(),
            ...(options.headers || {})
        }
    });
    const payload = await response.json().catch(() => ({
        success: false,
        error: { message: `Request failed with status ${response.status}.` }
    }));

    if (!response.ok || payload.success === false) {
        throw new Error(payload.error?.message || "Request failed.");
    }

    return payload;
}

/**
 * Initializes and triggers counter animations on balances.
 */
function initDashboardCounters() {
    const balanceElements = document.querySelectorAll(".balance-reveal");
    balanceElements.forEach(el => {
        const rawVal = Number.parseFloat(el.dataset.balance || "0.00");
        if (typeof window.animateCounter === "function") {
            window.animateCounter(el, rawVal, 1000);
        } else {
            el.textContent = formatCurrency(rawVal);
        }
    });
}

function initDashboardGreeting() {
    const hours = new Date().getHours();
    const greetText = document.getElementById("greeting-text");
    if (!greetText) return;

    const name = greetText.textContent.replace(/^Good day,\s*/i, "").trim();
    const firstName = name.split(/\s+/)[0] || name;
    let greeting = "Good evening";
    if (hours < 12) greeting = "Good morning";
    else if (hours < 18) greeting = "Good afternoon";

    greetText.textContent = `${greeting}, ${firstName}`;
}

function initSpendingAnalytics() {
    const config = getDashboardConfig();
    const canvas = document.getElementById("spending-doughnut-canvas");
    const chartPanel = document.getElementById("spending-chart-panel");
    const emptyState = document.getElementById("spending-empty-state");
    const recordList = document.getElementById("spending-record-list");
    const summary = config.spendingSummary || {};
    const hasRecords = Object.keys(summary).length > 0;

    if (!hasRecords) {
        if (chartPanel) chartPanel.style.display = "none";
        if (emptyState) emptyState.style.display = "flex";
        if (recordList) recordList.style.display = "none";
        return;
    }

    if (chartPanel) chartPanel.style.display = "block";
    if (emptyState) emptyState.style.display = "none";
    if (recordList) recordList.style.display = "flex";

    if (typeof window.createSpendingDonut === "function" && canvas) {
        window.createSpendingDonut(canvas, summary);
    }

    applyCategoryDotColors();
}

function applyCategoryDotColors() {
    const colors = window.CATEGORY_COLORS || {};
    document.querySelectorAll("[data-spending-category] .category-dot, .budget-item .category-dot").forEach(dot => {
        const item = dot.closest("[data-spending-category], .budget-item");
        const category = item?.dataset.spendingCategory || item?.dataset.budgetCategory;
        if (category && colors[category]) {
            dot.style.backgroundColor = colors[category];
        }
    });
}

function initDashboardAccountDetails() {
    const modal = document.getElementById("account-detail-modal");
    const stage = document.getElementById("account-flip-stage");
    const flipToggle = document.getElementById("account-flip-toggle");
    const accountButtons = document.querySelectorAll(".js-account-card");

    if (!modal || !stage || accountButtons.length === 0) return;

    accountButtons.forEach(button => {
        button.addEventListener("click", () => {
            showAccountDetails(button.dataset.accountId);
        });
    });

    document.querySelectorAll(".js-close-account-modal").forEach(button => {
        button.addEventListener("click", closeAccountDetails);
    });

    modal.addEventListener("click", event => {
        if (event.target === modal) closeAccountDetails();
    });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && modal.style.display === "flex") {
            closeAccountDetails();
        }
    });

    flipToggle?.addEventListener("click", () => {
        stage.classList.toggle("is-flipped");
        syncAccountFlipButton(true);
    });
}

async function showAccountDetails(accountId) {
    const modal = document.getElementById("account-detail-modal");
    const stage = document.getElementById("account-flip-stage");
    if (!modal || !stage || !accountId) return;

    setAccountModalLoading();
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
    window.setTimeout(() => modal.querySelector(".js-close-account-modal")?.focus(), 30);

    try {
        const [accountPayload, transactionPayload] = await Promise.all([
            fetchJson(`/api/accounts/${encodeURIComponent(accountId)}`),
            fetchJson(`/api/transactions?account_id=${encodeURIComponent(accountId)}`)
        ]);

        const account = accountPayload.data || {};
        const transactions = Array.isArray(transactionPayload.data) ? transactionPayload.data.slice(0, 10) : [];
        renderAccountDetails(account, transactions);
        window.setTimeout(() => {
            stage.classList.add("is-flipped");
            syncAccountFlipButton(true);
            document.getElementById("account-flip-toggle")?.focus();
        }, 180);
    } catch (error) {
        renderAccountError(error.message || "Account details could not be loaded.");
        stage.classList.add("is-flipped");
        syncAccountFlipButton();
    }
}

function closeAccountDetails() {
    const modal = document.getElementById("account-detail-modal");
    const stage = document.getElementById("account-flip-stage");
    if (!modal || !stage) return;

    modal.style.display = "none";
    document.body.style.overflow = "";
    stage.classList.remove("is-flipped");
    syncAccountFlipButton();
}

function syncAccountFlipButton(shouldFocus = false) {
    const stage = document.getElementById("account-flip-stage");
    const flipToggle = document.getElementById("account-flip-toggle");
    if (!stage || !flipToggle) return;
    flipToggle.textContent = stage.classList.contains("is-flipped") ? "Show Card" : "Show Details";

    const isFlipped = stage.classList.contains("is-flipped");
    const frontFace = document.getElementById("account-flip-front");
    const backFace = document.getElementById("account-flip-back");

    if (frontFace) {
        frontFace.setAttribute("aria-hidden", isFlipped ? "true" : "false");
        frontFace.inert = isFlipped;
    }
    if (backFace) {
        backFace.setAttribute("aria-hidden", isFlipped ? "false" : "true");
        backFace.inert = !isFlipped;
    }

    if (shouldFocus) {
        const focusTarget = isFlipped
            ? flipToggle
            : document.querySelector(".account-flip-front .js-close-account-modal");
        focusTarget?.focus();
    }
}

function setAccountModalLoading() {
    const stage = document.getElementById("account-flip-stage");
    stage?.classList.remove("is-flipped");
    setElementText("account-preview-name", "Account");
    setElementText("account-preview-balance", formatCurrency(0));
    setElementText("account-preview-number", "--------");
    setElementText("account-preview-sort", "-- -- --");
    setElementText("account-loading-text", "Preparing account details");
    setElementText("account-detail-title", "Account details");
    setElementText("account-detail-subtitle", "Latest account profile and transaction activity.");
    setElementText("account-detail-balance", formatCurrency(0));
    setElementText("account-detail-available", formatCurrency(0));
    setElementText("account-detail-status", "Loading");

    const detailGrid = document.getElementById("account-detail-grid");
    const transactionList = document.getElementById("account-transaction-list");
    if (detailGrid) detailGrid.innerHTML = `<div class="account-detail-empty">Loading account profile...</div>`;
    if (transactionList) transactionList.innerHTML = `<div class="account-detail-empty">Loading transactions...</div>`;
    syncAccountFlipButton();
}

function renderAccountDetails(account, transactions) {
    const accountName = account.nickname || `${titleCase(account.account_type)} Account`;
    const accountStatus = getAccountStatus(account);
    const detailLink = document.getElementById("account-detail-link");
    const statusPill = document.getElementById("account-detail-status");

    setElementText("account-preview-name", accountName);
    setElementText("account-preview-balance", formatCurrency(account.balance));
    setElementText("account-preview-number", account.account_number || "Not available");
    setElementText("account-preview-sort", account.sort_code || "Not available");
    setElementText("account-loading-text", "Account profile ready");
    setElementText("account-detail-title", accountName);
    setElementText(
        "account-detail-subtitle",
        `${titleCase(account.account_type) || "Bank"} account ending ${String(account.account_number || "----").slice(-4)}`
    );
    setElementText("account-detail-balance", formatCurrency(account.balance));
    setElementText("account-detail-available", formatCurrency(account.available_balance));
    setElementText("account-detail-status", accountStatus.label);

    if (statusPill) {
        statusPill.className = `account-status-pill ${accountStatus.className}`;
    }
    if (detailLink && account.id) {
        detailLink.href = `/accounts/${encodeURIComponent(account.id)}`;
    }

    renderAccountDetailGrid(account);
    renderAccountTransactions(account, transactions);
}

function getAccountStatus(account) {
    if (account.is_frozen) return { label: "Frozen", className: "warn" };
    if (account.is_active === false) return { label: "Inactive", className: "danger" };
    return { label: "Active", className: "good" };
}

function renderAccountDetailGrid(account) {
    const detailGrid = document.getElementById("account-detail-grid");
    if (!detailGrid) return;

    const rows = [
        ["Account ID", account.id],
        ["Nickname", account.nickname || "Not set"],
        ["Account Type", titleCase(account.account_type)],
        ["Account Number", account.account_number],
        ["Sort Code", account.sort_code],
        ["Currency", account.currency || "GBP"],
        ["Balance", formatCurrency(account.balance)],
        ["Available Balance", formatCurrency(account.available_balance)],
        ["Overdraft Limit", formatCurrency(account.overdraft_limit)],
        ["Active", account.is_active === false ? "No" : "Yes"],
        ["Frozen", account.is_frozen ? "Yes" : "No"],
        ["Opened", formatDate(account.created_at)]
    ];

    detailGrid.innerHTML = rows.map(([label, value]) => `
        <div class="account-detail-item">
            <span>${escapeHtml(label)}</span>
            <b>${escapeHtml(value || "Not available")}</b>
        </div>
    `).join("");
}

function renderAccountTransactions(account, transactions) {
    const transactionList = document.getElementById("account-transaction-list");
    if (!transactionList) return;

    if (!transactions.length) {
        transactionList.innerHTML = `<div class="account-detail-empty">No transactions found for this account yet.</div>`;
        return;
    }

    transactionList.innerHTML = transactions.map(transaction => {
        const view = getTransactionView(transaction, account.id);
        const description = transaction.description || transaction.reference || transaction.transaction_ref || "Transaction";
        const category = titleCase(transaction.category || "other");
        const status = titleCase(transaction.status || "completed");
        return `
            <div class="account-transaction-row ${view.className}">
                <div>
                    <h5>${escapeHtml(description)}</h5>
                    <div class="account-transaction-meta">${escapeHtml(formatDate(transaction.created_at))} · ${escapeHtml(category)} · ${escapeHtml(status)}</div>
                </div>
                <span class="account-transaction-amount">${view.prefix}${formatCurrency(view.amount)}</span>
            </div>
        `;
    }).join("");
}

function getTransactionView(transaction, accountId) {
    const fromId = transaction.from_account_id ? String(transaction.from_account_id) : "";
    const toId = transaction.to_account_id ? String(transaction.to_account_id) : "";
    const selectedId = String(accountId || "");
    const amount = Number.parseFloat(transaction.amount || 0);
    const fee = Number.parseFloat(transaction.fee || 0);

    if (transaction.transaction_type === "deposit" || (toId === selectedId && fromId !== selectedId)) {
        return { className: "credit", prefix: "+", amount };
    }

    if (fromId === selectedId && toId && toId !== selectedId) {
        return { className: "debit", prefix: "-", amount: amount + (Number.isFinite(fee) ? fee : 0) };
    }

    return { className: "internal", prefix: "", amount };
}

function renderAccountError(message) {
    setElementText("account-detail-title", "Account details unavailable");
    setElementText("account-detail-subtitle", message);
    setElementText("account-detail-status", "Error");

    const statusPill = document.getElementById("account-detail-status");
    const detailGrid = document.getElementById("account-detail-grid");
    const transactionList = document.getElementById("account-transaction-list");
    if (statusPill) statusPill.className = "account-status-pill danger";
    if (detailGrid) detailGrid.innerHTML = `<div class="account-detail-empty">${escapeHtml(message)}</div>`;
    if (transactionList) transactionList.innerHTML = `<div class="account-detail-empty">Try opening the account again in a moment.</div>`;
}

function initDashboardSafetyCenter() {
    const card = document.getElementById("account-safety-card");
    const runButton = document.getElementById("safety-run-check");
    if (!card) return;

    card.querySelectorAll(".safety-check-item").forEach(item => {
        item.addEventListener("click", () => {
            const action = item.dataset.safetyAction;
            if (action === "cloud") {
                notify("Cloud route check is available from the Run Check button.", "info");
                return;
            }
            if (item.dataset.href) {
                window.location.href = item.dataset.href;
            }
        });
    });

    runButton?.addEventListener("click", () => runSafetyCheck(card, runButton));
}

async function runSafetyCheck(card, button) {
    const progress = document.getElementById("safety-progress-fill");
    const status = document.getElementById("safety-check-status");
    const score = document.getElementById("safety-score");
    const mfaEnabled = card.dataset.mfaEnabled === "true";

    setButtonLoading(button, true, "Checking...");
    if (status) status.textContent = "Checking cloud route, database, and alerts...";
    if (progress) progress.style.width = "35%";

    try {
        const [health, notifications] = await Promise.all([
            fetchJson("/health"),
            fetchJson("/api/notifications").catch(() => ({ data: [] }))
        ]);

        const unread = Array.isArray(notifications.data)
            ? notifications.data.filter(item => !item.is_read).length
            : Number.parseInt(card.dataset.unreadAlerts || "0", 10);
        const cloudHealthy = health.status === "healthy";
        const dbConnected = health.db === "connected";
        const nextScore = Math.min(
            100,
            60 + (cloudHealthy ? 18 : 0) + (dbConnected ? 12 : 0) + (unread === 0 ? 5 : 0) + (mfaEnabled ? 5 : 0)
        );

        updateSafetyItem("cloud", `Active route: ${titleCase(health.server || card.dataset.cloud || "aws")}`, cloudHealthy ? "Live" : "Check", cloudHealthy ? "good" : "warn");
        updateSafetyItem("alerts", `${unread} alert${unread === 1 ? "" : "s"} waiting`, unread === 0 ? "Clear" : "Review", unread === 0 ? "good" : "warn");
        updateSafetyItem("mfa", mfaEnabled ? "Enabled on this profile" : "Not enabled yet", mfaEnabled ? "OK" : "Action", mfaEnabled ? "good" : "warn");

        if (score) score.textContent = nextScore;
        if (progress) progress.style.width = `${nextScore}%`;
        if (status) status.textContent = cloudHealthy && dbConnected
            ? "Live check complete. Banking route and database are healthy."
            : "Live check complete. Review the highlighted safety item.";
        notify("Security check complete.", cloudHealthy && dbConnected ? "accent" : "info");
    } catch (error) {
        if (status) status.textContent = "Live check could not complete. Please try again.";
        if (progress) progress.style.width = "52%";
        updateSafetyItem("cloud", "Route check unavailable", "Retry", "warn");
        notify(error.message || "Security check failed.", "error");
    } finally {
        setButtonLoading(button, false, "Checking...");
    }
}

function updateSafetyItem(key, metaText, pillText, state) {
    const meta = document.querySelector(`[data-safety-meta="${key}"]`);
    const pill = document.querySelector(`[data-safety-pill="${key}"]`);
    if (meta) meta.textContent = metaText;
    if (pill) {
        pill.textContent = pillText;
        pill.className = `safety-pill ${state}`;
    }
}

function initDashboardForms() {
    initModalDismissal();

    document.getElementById("btn-open-deposit")?.addEventListener("click", () => openModal("deposit-modal"));
    document.querySelector(".js-close-deposit-modal")?.addEventListener("click", () => closeModal("deposit-modal"));
    document.getElementById("deposit-form")?.addEventListener("submit", handleDeposit);

    document.querySelectorAll(".js-open-budget-modal").forEach(button => {
        button.addEventListener("click", () => showBudgetModal());
    });
    document.querySelector(".js-close-budget-modal")?.addEventListener("click", () => closeModal("budget-modal"));
    document.getElementById("budget-form")?.addEventListener("submit", handleBudgetSubmit);

    document.querySelectorAll(".js-edit-budget").forEach(button => {
        button.addEventListener("click", () => showBudgetModal(button.closest(".budget-item")));
    });
    document.querySelectorAll(".js-delete-budget").forEach(button => {
        button.addEventListener("click", () => deleteBudget(button.closest(".budget-item")));
    });

    document.querySelectorAll(".js-open-goal-modal").forEach(button => {
        button.addEventListener("click", () => showGoalModal());
    });
    document.querySelector(".js-close-goal-modal")?.addEventListener("click", () => closeModal("goal-modal"));
    document.getElementById("goal-form")?.addEventListener("submit", handleGoalSubmit);

    document.querySelectorAll(".js-edit-goal").forEach(button => {
        button.addEventListener("click", () => showGoalModal(button.closest(".goal-item")));
    });
    document.querySelectorAll(".js-delete-goal").forEach(button => {
        button.addEventListener("click", () => deleteGoal(button.closest(".goal-item")));
    });
    document.querySelectorAll(".js-open-goal-progress").forEach(button => {
        button.addEventListener("click", () => showGoalProgressModal(button.closest(".goal-item")));
    });
    document.querySelector(".js-close-goal-progress-modal")?.addEventListener("click", () => closeModal("goal-progress-modal"));
    document.getElementById("goal-progress-form")?.addEventListener("submit", handleGoalProgressSubmit);

    window.showDepositModal = () => openModal("deposit-modal");
    window.closeDepositModal = () => closeModal("deposit-modal");
}

function initModalDismissal() {
    const modalIds = ["deposit-modal", "budget-modal", "goal-modal", "goal-progress-modal"];

    modalIds.forEach(id => {
        const modal = document.getElementById(id);
        if (!modal) return;
        modal.addEventListener("click", event => {
            if (event.target === modal) {
                closeModal(id);
            }
        });
    });

    document.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        modalIds.forEach(id => {
            const modal = document.getElementById(id);
            if (modal && modal.style.display === "flex") {
                closeModal(id);
            }
        });
    });
}

function showBudgetModal(item = null) {
    const form = document.getElementById("budget-form");
    const title = document.getElementById("budget-modal-title");
    const idInput = document.getElementById("budget-id");
    const categorySelect = document.getElementById("budget-category");
    const limitInput = document.getElementById("budget-limit");

    if (form) form.reset();
    if (title) title.textContent = item ? "Edit Category Budget" : "Add Category Budget";
    if (idInput) idInput.value = item?.dataset.budgetId || "";
    if (categorySelect && item?.dataset.budgetCategory) categorySelect.value = item.dataset.budgetCategory;
    if (limitInput) limitInput.value = item?.dataset.budgetLimit || "";

    openModal("budget-modal");
}

async function handleBudgetSubmit(event) {
    event.preventDefault();
    const submitBtn = document.getElementById("btn-budget-submit");
    const budgetId = document.getElementById("budget-id")?.value;
    const body = {
        category: document.getElementById("budget-category")?.value,
        limit_amount: document.getElementById("budget-limit")?.value,
        month: document.getElementById("budget-month")?.value
    };

    setButtonLoading(submitBtn, true);
    try {
        await fetchJson(
            budgetId ? `/api/dashboard/budgets/${budgetId}` : "/api/dashboard/budgets",
            {
                method: budgetId ? "PATCH" : "POST",
                body: JSON.stringify(body)
            }
        );
        notify("Budget saved.", "accent");
        closeModal("budget-modal");
        reloadSoon();
    } catch (error) {
        notify(error.message, "error");
        setButtonLoading(submitBtn, false);
    }
}

async function handleDeposit(event) {
    event.preventDefault();
    const submitBtn = document.getElementById("btn-dep-submit");
    const body = {
        to_account_id: document.getElementById("dep-account")?.value,
        amount: document.getElementById("dep-amount")?.value
    };

    setButtonLoading(submitBtn, true, "Depositing...");
    try {
        await fetchJson("/api/transactions/deposit", {
            method: "POST",
            body: JSON.stringify(body)
        });
        notify("Deposit processed successfully.", "accent");
        if (typeof window.triggerConfetti === "function") {
            window.triggerConfetti();
        }
        closeModal("deposit-modal");
        reloadSoon(1200);
    } catch (error) {
        notify(error.message, "error");
        setButtonLoading(submitBtn, false, "Depositing...");
    }
}

async function deleteBudget(item) {
    if (!item?.dataset.budgetId) return;
    if (!window.confirm("Delete this budget for the month?")) return;

    try {
        await fetchJson(`/api/dashboard/budgets/${item.dataset.budgetId}`, { method: "DELETE" });
        notify("Budget deleted.", "info");
        reloadSoon();
    } catch (error) {
        notify(error.message, "error");
    }
}

function showGoalModal(item = null) {
    const form = document.getElementById("goal-form");
    const title = document.getElementById("goal-modal-title");
    const idInput = document.getElementById("goal-id");
    const accountSelect = document.getElementById("goal-account");
    const nameInput = document.getElementById("goal-name");
    const targetInput = document.getElementById("goal-target");
    const currentInput = document.getElementById("goal-current");
    const dateInput = document.getElementById("goal-date");

    if (form) form.reset();
    if (title) title.textContent = item ? "Edit Savings Goal" : "Add Savings Goal";
    if (idInput) idInput.value = item?.dataset.goalId || "";
    if (accountSelect && item?.dataset.goalAccountId) accountSelect.value = item.dataset.goalAccountId;
    if (nameInput) nameInput.value = item?.dataset.goalName || "";
    if (targetInput) targetInput.value = item?.dataset.goalTarget || "";
    if (currentInput) currentInput.value = item?.dataset.goalCurrent || "0.00";
    if (dateInput) dateInput.value = item?.dataset.goalDate || "";

    openModal("goal-modal");
}

async function handleGoalSubmit(event) {
    event.preventDefault();
    const submitBtn = document.getElementById("btn-goal-submit");
    const goalId = document.getElementById("goal-id")?.value;
    const body = {
        account_id: document.getElementById("goal-account")?.value,
        name: document.getElementById("goal-name")?.value,
        target_amount: document.getElementById("goal-target")?.value,
        current_amount: document.getElementById("goal-current")?.value,
        target_date: document.getElementById("goal-date")?.value
    };

    setButtonLoading(submitBtn, true);
    try {
        await fetchJson(
            goalId ? `/api/dashboard/goals/${goalId}` : "/api/dashboard/goals",
            {
                method: goalId ? "PATCH" : "POST",
                body: JSON.stringify(body)
            }
        );
        notify("Savings goal saved.", "accent");
        closeModal("goal-modal");
        reloadSoon();
    } catch (error) {
        notify(error.message, "error");
        setButtonLoading(submitBtn, false);
    }
}

function showGoalProgressModal(item) {
    if (!item?.dataset.goalId) return;

    const idInput = document.getElementById("goal-progress-id");
    const amountInput = document.getElementById("goal-progress-amount");
    const nameLabel = document.getElementById("goal-progress-name");

    if (idInput) idInput.value = item.dataset.goalId;
    if (amountInput) amountInput.value = "";
    if (nameLabel) {
        nameLabel.textContent = `${item.dataset.goalName || "Savings goal"}: ${formatCurrency(item.dataset.goalCurrent)} saved`;
    }

    openModal("goal-progress-modal");
}

async function handleGoalProgressSubmit(event) {
    event.preventDefault();
    const submitBtn = document.getElementById("btn-goal-progress-submit");
    const goalId = document.getElementById("goal-progress-id")?.value;
    const amount = document.getElementById("goal-progress-amount")?.value;

    if (!goalId) return;

    setButtonLoading(submitBtn, true, "Adding...");
    try {
        await fetchJson(`/api/dashboard/goals/${goalId}/contribute`, {
            method: "POST",
            body: JSON.stringify({ amount })
        });
        notify("Goal progress updated.", "accent");
        closeModal("goal-progress-modal");
        reloadSoon();
    } catch (error) {
        notify(error.message, "error");
        setButtonLoading(submitBtn, false, "Adding...");
    }
}

async function deleteGoal(item) {
    if (!item?.dataset.goalId) return;
    if (!window.confirm("Delete this savings goal?")) return;

    try {
        await fetchJson(`/api/dashboard/goals/${item.dataset.goalId}`, { method: "DELETE" });
        notify("Savings goal deleted.", "info");
        reloadSoon();
    } catch (error) {
        notify(error.message, "error");
    }
}

/**
 * Manages onboarding checklist click and visual state transitions.
 */
function initOnboardingChecklist() {
    const checklistCard = document.getElementById("onboarding-checklist-card");
    const checklistItems = document.querySelectorAll(".checklist-checkbox");

    if (!checklistCard || checklistItems.length === 0) return;

    checklistItems.forEach(item => {
        item.addEventListener("change", (e) => {
            const label = e.target.nextElementSibling;
            if (e.target.checked) {
                label.style.textDecoration = "line-through";
                label.style.color = "var(--text-muted)";
            } else {
                label.style.textDecoration = "none";
                label.style.color = "var(--text-primary)";
            }

            const allChecked = Array.from(checklistItems).every(i => i.checked);
            if (allChecked) {
                setTimeout(() => {
                    checklistCard.style.opacity = "0";
                    checklistCard.style.transform = "translateY(-10px)";
                    checklistCard.style.transition = "all 0.4s ease";
                    checklistCard.addEventListener("transitionend", () => {
                        checklistCard.remove();
                    });
                }, 1000);
            }
        });
    });
}
