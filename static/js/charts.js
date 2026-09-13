/**
 * NovaPay Chart.js Configurations and Utilities
 */

const CATEGORY_COLORS = {
    salary:        '#00C896', // emerald
    bills:         '#0A2463', // deep navy
    shopping:      '#F59E0B', // amber
    eating_out:    '#EF4444', // red
    transport:     '#38BDF8', // sky blue
    entertainment: '#8B5CF6', // purple
    health:        '#EC4899', // pink
    travel:        '#10B981', // green
    other:         '#64748B'  // grey
};

/**
 * Creates a spending categories donut chart.
 * @param {HTMLCanvasElement} canvas The canvas element.
 * @param {Object} dataObj Object mapping category keys to values.
 */
function createSpendingDonut(canvas, dataObj) {
    if (!canvas || !dataObj) return null;
    
    const labels = Object.keys(dataObj).map(k => k.replace("_", " ").toUpperCase());
    const values = Object.values(dataObj);
    const backgroundColors = Object.keys(dataObj).map(k => CATEGORY_COLORS[k] || CATEGORY_COLORS.other);
    
    return new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: backgroundColors,
                borderWidth: 2,
                borderColor: 'var(--card)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'var(--text-secondary)',
                        font: { family: 'Inter', size: 12 }
                    }
                }
            },
            cutout: '70%'
        }
    });
}

/**
 * Creates a minimal 30-day sparkline balance trend chart.
 * @param {HTMLCanvasElement} canvas The canvas element.
 * @param {Array<number>} dataPoints Array of numbers.
 */
function createBalanceSparkline(canvas, dataPoints) {
    if (!canvas || !dataPoints) return null;
    
    return new Chart(canvas, {
        type: 'line',
        data: {
            labels: dataPoints.map((_, i) => i),
            datasets: [{
                data: dataPoints,
                borderColor: '#00C896',
                borderWidth: 2,
                fill: false,
                tension: 0.3,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                y: { display: false }
            }
        }
    });
}

window.createSpendingDonut = createSpendingDonut;
window.createBalanceSparkline = createBalanceSparkline;
window.CATEGORY_COLORS = CATEGORY_COLORS;
