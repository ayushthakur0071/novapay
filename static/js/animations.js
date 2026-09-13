/**
 * NovaPay Interactive Animation Engine Helpers
 */

/**
 * Animates a numeric counter from 0 to target value.
 * @param {HTMLElement} el The DOM element to write the text to.
 * @param {number} target The target currency amount.
 * @param {number} duration The duration in milliseconds.
 */
function animateCounter(el, target, duration = 1200) {
    if (!el) return;
    let start = 0;
    const step = target / (duration / 16); // roughly 60 fps
    
    const tick = () => {
        start = Math.min(start + step, target);
        // Format as GBP currency: £X,XXX.XX
        el.textContent = "£" + start.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        if (start < target) {
            requestAnimationFrame(tick);
        }
    };
    requestAnimationFrame(tick);
}

/**
 * Spawns 40 confetti particles from the center of the screen flying outwards.
 */
function triggerConfetti() {
    const colors = ['#00C896', '#0A2463', '#1E3A8A', '#F59E0B', '#EF4444', '#E2E8F0'];
    const particleCount = 40;
    const container = document.body;

    for (let i = 0; i < particleCount; i++) {
        const p = document.createElement('div');
        p.classList.add('confetti-particle');
        
        // Random style and color
        const color = colors[Math.floor(randomRange(0, colors.length))];
        p.style.backgroundColor = color;
        
        // Random flight targets
        const angle = randomRange(0, Math.PI * 2);
        const distance = randomRange(80, 260);
        const dx = Math.cos(angle) * distance;
        const dy = Math.sin(angle) * distance;
        const rot = randomRange(180, 720);
        
        // Pass variables to CSS keyframes
        p.style.setProperty('--dx', `${dx}px`);
        p.style.setProperty('--dy', `${dy}px`);
        p.style.setProperty('--rot', `${rot}deg`);
        
        // Center position
        p.style.left = '50vw';
        p.style.top = '50vh';
        
        container.appendChild(p);
        
        // Cleanup after animation completes (1.2s in CSS)
        setTimeout(() => p.remove(), 1250);
    }
}

function randomRange(min, max) {
    return Math.random() * (max - min) + min;
}

// Export for module systems or attach to window for global access
window.animateCounter = animateCounter;
window.triggerConfetti = triggerConfetti;
