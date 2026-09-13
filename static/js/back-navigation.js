/**
 * Shared back navigation for NovaPay pages.
 */

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-back-button]").forEach((button) => {
        button.addEventListener("click", () => {
            const fallbackUrl = button.dataset.fallbackUrl || "/";
            let canUseHistory = false;

            try {
                const referrer = document.referrer ? new URL(document.referrer) : null;
                canUseHistory = Boolean(
                    referrer &&
                    referrer.origin === window.location.origin &&
                    referrer.href !== window.location.href &&
                    window.history.length > 1
                );
            } catch (error) {
                canUseHistory = false;
            }

            if (canUseHistory) {
                window.history.back();
                return;
            }

            window.location.href = fallbackUrl;
        });
    });
});
