/**
 * NovaPay Multi-Step Transfer Wizard JavaScript
 */

document.addEventListener("DOMContentLoaded", () => {
    initTransferWizard();
});

function initTransferWizard() {
    const wizardForm = document.getElementById("wizard-steps-container") || document.getElementById("transfer-wizard-form");
    if (!wizardForm) return;

    const steps = document.querySelectorAll(".wizard-step");
    const progressFill = document.querySelector(".progress-bar-fill");
    
    let currentStep = 1;
    
    // Step elements
    const btnNext1 = document.getElementById("btn-next-1");
    const btnNext2 = document.getElementById("btn-next-2");
    const btnPrev2 = document.getElementById("btn-prev-2");
    const btnPrev3 = document.getElementById("btn-prev-3");
    const btnConfirmTransfer = document.getElementById("btn-confirm-transfer");
    const transferConfirmModal = document.getElementById("transfer-confirm-modal");
    const btnCancelTransferModal = document.getElementById("btn-cancel-transfer-modal");
    const btnSendTransferModal = document.getElementById("btn-send-transfer-modal");
    let transferInFlight = false;
    
    // Step inputs
    const sourceAccSelect = document.getElementById("from_account_id");
    const recipientTypeRadios = document.querySelectorAll('input[name="recipient_type"]');
    const existingRecipientSelect = document.getElementById("beneficiary_id");
    const existingPayeeDiv = document.getElementById("existing-payee-details");
    
    // Custom payee inputs
    const customPayeeDiv = document.getElementById("custom-payee-details");
    const customNameInput = document.getElementById("payee_name");
    const customAccInput = document.getElementById("account_number");
    const customSortInput = document.getElementById("sort_code");
    
    const amountInput = document.getElementById("amount");
    const referenceInput = document.getElementById("reference");
    const categorySelect = document.getElementById("category");
    
    // Toggle Custom Payee Fields
    const selfPayeeDiv = document.getElementById("self-payee-details");
    const destinationAccSelect = document.getElementById("to_account_id");
    const selfInfoCard = document.getElementById("self-account-info-card");
    
    function updateRecipientUI() {
        const selectedVal = Array.from(recipientTypeRadios).find(r => r.checked)?.value || "existing";
        
        if (selectedVal === "existing") {
            if (customPayeeDiv) customPayeeDiv.style.display = "none";
            if (selfPayeeDiv) selfPayeeDiv.style.display = "none";
            if (selfInfoCard) selfInfoCard.style.display = "none";
            if (existingPayeeDiv) existingPayeeDiv.style.display = "block";
        } else if (selectedVal === "self") {
            if (customPayeeDiv) customPayeeDiv.style.display = "none";
            if (selfPayeeDiv) selfPayeeDiv.style.display = "block";
            if (existingPayeeDiv) existingPayeeDiv.style.display = "none";
            filterSelfTransferOptions();
            if (destinationAccSelect && destinationAccSelect.value) {
                if (selfInfoCard) selfInfoCard.style.display = "flex";
            } else {
                if (selfInfoCard) selfInfoCard.style.display = "none";
            }
        } else { // custom
            if (customPayeeDiv) customPayeeDiv.style.display = "block";
            if (selfPayeeDiv) selfPayeeDiv.style.display = "none";
            if (selfInfoCard) selfInfoCard.style.display = "none";
            if (existingPayeeDiv) existingPayeeDiv.style.display = "none";
        }
    }

    recipientTypeRadios.forEach(radio => {
        radio.addEventListener("change", updateRecipientUI);
    });

    // Run sync immediately on wizard setup
    updateRecipientUI();

    if (destinationAccSelect) {
        destinationAccSelect.addEventListener("change", (e) => {
            const selectedOpt = e.target.options[e.target.selectedIndex];
            if (selectedOpt && selectedOpt.value) {
                document.getElementById("self-sort-code").textContent = selectedOpt.dataset.sortCode || "";
                document.getElementById("self-account-number").textContent = selectedOpt.dataset.accountNumber || "";
                document.getElementById("self-balance").textContent = "£" + parseFloat(selectedOpt.dataset.balance || "0").toFixed(2);
                if (selfInfoCard) selfInfoCard.style.display = "flex";
            } else {
                if (selfInfoCard) selfInfoCard.style.display = "none";
            }
        });
    }

    function filterSelfTransferOptions() {
        const fromVal = sourceAccSelect.value;
        if (!destinationAccSelect) return;
        
        Array.from(destinationAccSelect.options).forEach((opt, idx) => {
            if (idx === 0) return; // Keep prompt enabled
            if (opt.value === fromVal) {
                opt.disabled = true;
                opt.style.display = "none";
            } else {
                opt.disabled = false;
                opt.style.display = "block";
            }
        });
        
        if (destinationAccSelect.value === fromVal || !destinationAccSelect.value) {
            destinationAccSelect.value = "";
            if (selfInfoCard) selfInfoCard.style.display = "none";
        }
    }
    
    if (sourceAccSelect) {
        sourceAccSelect.addEventListener("change", () => {
            filterSelfTransferOptions();
        });
    }

    // Step 1 to 2 Navigation
    if (btnNext1) {
        btnNext1.addEventListener("click", () => {
            // Validate Step 1
            if (!sourceAccSelect.value) {
                showToast("Please select a source account.", "error");
                shakeElement(sourceAccSelect);
                return;
            }
            
            const selectedType = Array.from(recipientTypeRadios).find(r => r.checked)?.value;
            if (selectedType === "existing") {
                if (!existingRecipientSelect.value) {
                    showToast("Please select a recipient.", "error");
                    shakeElement(existingRecipientSelect);
                    return;
                }
            } else if (selectedType === "self") {
                if (!destinationAccSelect.value) {
                    showToast("Please select a destination account.", "error");
                    shakeElement(destinationAccSelect);
                    return;
                }
            } else {
                if (!customNameInput.value || !customAccInput.value || !customSortInput.value) {
                    showToast("Please complete payee bank details.", "error");
                    if (!customNameInput.value) shakeElement(customNameInput);
                    if (!customAccInput.value) shakeElement(customAccInput);
                    if (!customSortInput.value) shakeElement(customSortInput);
                    return;
                }
                if (customAccInput.value.length !== 8) {
                    showToast("Account number must be exactly 8 digits.", "error");
                    shakeElement(customAccInput);
                    return;
                }
                if (!/^\d{2}-\d{2}-\d{2}$/.test(customSortInput.value)) {
                    showToast("Sort code must match XX-XX-XX format.", "error");
                    shakeElement(customSortInput);
                    return;
                }
            }
            
            goToStep(2);
        });
    }

    // Transfer Method fee listener
    const transferMethodSelect = document.getElementById("transfer_method");
    const transferHint = document.getElementById("transfer-charge-hint");
    const feeMap = { "IMPS": 1.50, "NEFT": 0.50, "RTGS": 5.00, "OVERDRAFT": 10.00 };
    
    if (transferMethodSelect) {
        transferMethodSelect.addEventListener("change", (e) => {
            const fee = feeMap[e.target.value] || 1.50;
            if (transferHint) {
                transferHint.innerHTML = `* An additional fee of <strong style="color:var(--accent);">£${fee.toFixed(2)}</strong> will be deducted from your account.`;
            }
        });
    }

    // Step 2 to 3 Navigation
    if (btnNext2) {
        btnNext2.addEventListener("click", () => {
            const amount = parseFloat(amountInput.value || "0");
            if (isNaN(amount) || amount <= 0) {
                showToast("Please input a valid amount.", "error");
                shakeElement(amountInput);
                return;
            }
            
            // Validate balance
            const selectedOption = sourceAccSelect.options[sourceAccSelect.selectedIndex];
            const balance = parseFloat(selectedOption.dataset.balance || "0");
            const overdraft = parseFloat(selectedOption.dataset.overdraft || "0");
            
            const selectedType = Array.from(recipientTypeRadios).find(r => r.checked)?.value;
            
            let selectedMethod = "IMPS";
            let fee = 1.50;
            
            if (selectedType === "self") {
                selectedMethod = "INTERNAL";
                fee = 0.00;
            } else if (transferMethodSelect) {
                selectedMethod = transferMethodSelect.value;
                fee = feeMap[selectedMethod] || 1.50;
            }
            
            const totalDebit = amount + fee;
            
            if (totalDebit > balance + overdraft) {
                if (selectedType === "self") {
                    showToast(`Insufficient available funds (£${totalDebit.toFixed(2)}).`, "error");
                } else {
                    showToast(`Insufficient available funds to cover amount + ${selectedMethod} fee (£${totalDebit.toFixed(2)}).`, "error");
                }
                shakeElement(amountInput);
                return;
            }
            
            // Populate Confirmation step card
            document.getElementById("confirm-method").textContent = selectedMethod;
            document.getElementById("confirm-fee").textContent = "£" + fee.toFixed(2);
            document.getElementById("confirm-total").textContent = "£" + totalDebit.toFixed(2);
            document.getElementById("confirm-from").textContent = selectedOption.text;
            
            if (selectedType === "existing") {
                document.getElementById("confirm-to").textContent = existingRecipientSelect.options[existingRecipientSelect.selectedIndex].text;
            } else if (selectedType === "self") {
                document.getElementById("confirm-to").textContent = destinationAccSelect.options[destinationAccSelect.selectedIndex].text;
            } else {
                document.getElementById("confirm-to").textContent = `${customNameInput.value} (${customSortInput.value} / ${customAccInput.value})`;
            }
            
            goToStep(3);
            if (btnConfirmTransfer) btnConfirmTransfer.focus();
        });
    }

    // Back Navigation
    if (btnPrev2) btnPrev2.addEventListener("click", () => goToStep(1));
    if (btnPrev3) btnPrev3.addEventListener("click", () => goToStep(2));
    
    // Confirm Transfer Button Trigger
    if (btnConfirmTransfer) {
        btnConfirmTransfer.addEventListener("click", () => {
            requestTransferConfirmation();
        });
    }

    if (btnCancelTransferModal) {
        btnCancelTransferModal.addEventListener("click", closeTransferConfirmModal);
    }

    if (btnSendTransferModal) {
        btnSendTransferModal.addEventListener("click", () => {
            if (transferInFlight) return;
            executeTransfer();
        });
    }

    if (transferConfirmModal) {
        transferConfirmModal.addEventListener("click", (e) => {
            if (e.target === transferConfirmModal && !transferInFlight) {
                closeTransferConfirmModal();
            }
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && transferConfirmModal && transferConfirmModal.style.display === "flex" && !transferInFlight) {
            closeTransferConfirmModal();
        }
    });
    
    function goToStep(stepNum) {
        steps.forEach(step => {
            const isActive = parseInt(step.dataset.step) === stepNum;
            step.classList.toggle("active", isActive);
            step.style.display = isActive ? "block" : "none";
        });
        
        // Progress bar percentage
        if (progressFill) {
            const pct = ((stepNum - 1) / (steps.length - 1)) * 100;
            progressFill.style.setProperty("--progress", `${pct}%`);
            progressFill.style.width = `${pct}%`;
        }
        currentStep = stepNum;
    }

    function requestTransferConfirmation() {
        populateTransferConfirmModal();
        openTransferConfirmModal();
    }

    function populateTransferConfirmModal() {
        const amount = parseFloat(amountInput.value || "0");
        const amountText = Number.isFinite(amount) ? `£${amount.toFixed(2)}` : "£0.00";
        const reference = (referenceInput.value || "").trim() || "Not supplied";

        setText("modal-confirm-from", document.getElementById("confirm-from")?.textContent || "-");
        setText("modal-confirm-to", document.getElementById("confirm-to")?.textContent || "-");
        setText("modal-confirm-amount", amountText);
        setText("modal-confirm-fee", document.getElementById("confirm-fee")?.textContent || "£0.00");
        setText("modal-confirm-total", document.getElementById("confirm-total")?.textContent || amountText);
        setText("modal-confirm-reference", reference);
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function openTransferConfirmModal() {
        if (!transferConfirmModal) return;
        transferConfirmModal.style.display = "flex";
        if (btnSendTransferModal) btnSendTransferModal.focus();
    }

    function closeTransferConfirmModal() {
        if (!transferConfirmModal) return;
        transferConfirmModal.style.display = "none";
        if (!transferInFlight && btnConfirmTransfer) {
            btnConfirmTransfer.focus();
        }
    }

    function setTransferLoading(isLoading) {
        transferInFlight = isLoading;

        if (btnConfirmTransfer) {
            btnConfirmTransfer.disabled = isLoading;
            btnConfirmTransfer.textContent = isLoading ? "Sending..." : "Confirm Transfer";
        }

        if (btnSendTransferModal) {
            btnSendTransferModal.disabled = isLoading;
            btnSendTransferModal.textContent = isLoading ? "Sending..." : "Send Money";
        }

        if (btnCancelTransferModal) {
            btnCancelTransferModal.disabled = isLoading;
        }
    }

    function executeTransfer() {
        if (transferInFlight) return;

        const selectedType = Array.from(recipientTypeRadios).find(r => r.checked)?.value;
        const selectedMethod = transferMethodSelect ? transferMethodSelect.value : "IMPS";
        
        let url = "/api/transactions/send";
        let body = {};
        
        if (selectedType === "self") {
            url = "/api/transactions/transfer";
            body = {
                from_account_id: sourceAccSelect.value,
                to_account_id: destinationAccSelect.value,
                amount: amountInput.value,
                reference: referenceInput.value
            };
        } else {
            body = {
                from_account_id: sourceAccSelect.value,
                amount: amountInput.value,
                reference: referenceInput.value,
                category: categorySelect.value,
                transfer_method: selectedMethod
            };
            if (selectedType === "existing") {
                body.beneficiary_id = existingRecipientSelect.value;
            } else {
                body.payee_name = customNameInput.value;
                body.account_number = customAccInput.value;
                body.sort_code = customSortInput.value;
            }
        }
        
        // Disable inputs during processing
        setTransferLoading(true);
        
        // CSRF Token
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute("content");
        
        fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken
            },
            body: JSON.stringify(body)
        })
        .then(async r => {
            const contentType = r.headers.get("content-type") || "";
            const payload = contentType.includes("application/json")
                ? await r.json()
                : { success: false, error: { message: `Transfer failed with status ${r.status}.` } };

            if (!r.ok && payload.success !== true) {
                payload.success = false;
            }

            return payload;
        })
        .then(res => {
            if (res.success) {
                if (typeof window.triggerConfetti === "function") {
                    window.triggerConfetti();
                }
                showToast("Transfer completed successfully!", "accent");
                closeTransferConfirmModal();
                
                // Show success receipt
                document.getElementById("wizard-steps-container").style.display = "none";
                const pBar = document.getElementById("progress-bar-wrapper");
                if (pBar) pBar.style.display = "none";
                const receipt = document.getElementById("success-receipt");
                if (receipt) receipt.style.display = "block";
            } else {
                showToast(res.error.message || "Transfer failed.", "error");
                setTransferLoading(false);
                closeTransferConfirmModal();
            }
        })
        .catch(err => {
            showToast("Network error. Transfer failed.", "error");
            setTransferLoading(false);
            closeTransferConfirmModal();
        });
    }
}

function shakeElement(el) {
    if (!el) return;
    el.classList.add("shake");
    el.addEventListener("animationend", () => {
        el.classList.remove("shake");
    }, { once: true });
}
