/**
 * NovaPay Server Telemetry Monitoring Module
 */

document.addEventListener("DOMContentLoaded", () => {
    initServerTelemetry();
});

function initServerTelemetry() {
    const statusText = document.getElementById("server-status-text");
    const activeDot = document.getElementById("server-status-dot");
    
    if (!statusText || !activeDot) return;
    
    const pollStatus = () => {
        fetch("/health")
            .then(r => r.json())
            .then(data => {
                // Update header status indicators
                statusText.textContent = `${data.server.toUpperCase()} Active`;
                activeDot.className = "status-dot green";
                
                // Update uptime / db status labels if they exist
                const dbLabel = document.getElementById("health-db-status");
                if (dbLabel) dbLabel.textContent = data.db.toUpperCase();
                
                const upLabel = document.getElementById("health-uptime");
                if (upLabel) upLabel.textContent = `${(data.uptime / 3600).toFixed(2)} hrs`;
            })
            .catch(() => {
                statusText.textContent = "Failover Degraded";
                activeDot.className = "status-dot red";
            });
    };
    
    pollStatus();
    setInterval(pollStatus, 15000); // Poll status every 15s
}
