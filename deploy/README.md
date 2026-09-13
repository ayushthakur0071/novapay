# NovaPay Real-Time Multi-Cloud Deployment & Connection Guide

This guide explains how to connect NovaPay to live, real-time host instances on **Amazon Web Services (AWS)** and **Microsoft Azure**.

---

## 🏗️ Architecture

```
                                  [ User / Browser ]
                                          │
                                          ▼
                            [ NovaPay Proxy Balancer ]
                               (proxy_server.py :8080)
                                    │             │
                ┌───────────────────┘             └───────────────────┐
                │ (Active Route)                                      │ (Passive Route / Failover)
                ▼                                                     ▼
     ┌────────────────────────┐                            ┌────────────────────────┐
     │   AWS Cloud Node       │                            │   Azure Cloud Node     │
     │  (AWS App Runner / ECS)│                            │  (Azure App Service)   │
     │  https://novapay-aws...│                            │  https://novapay-azure.│
     └──────────┬─────────────┘                            └──────────┬─────────────┘
                │                                                     │
                │        [ Real-Time Telemetry Daemon ]               │
                │           (monitoring_daemon.py)                    │
                │         Pings /health every 30 seconds              │
                │                                                     │
                └───────────────────────┬─────────────────────────────┘
                                        ▼
                            [ Supabase PostgreSQL ]
                          (Multi-Cloud Shared Database)
```

---

## Option 1: Connecting to Existing AWS & Azure Cloud Hosts

If you already have running host instances or public domain endpoints on AWS and Azure:

1. Open your `.env` file in the project root.
2. Update `AWS_URL` and `AZURE_URL` with your real cloud endpoints (include `https://`):
   ```env
   # Real-Time Cloud Host Endpoints
   AWS_URL=https://novapay-aws.your-app-runner-id.eu-west-1.awsapprunner.com
   AZURE_URL=https://novapay-azure.azurewebsites.net
   PRIMARY_CLOUD=aws

   # Proxy and Daemon Settings
   PROXY_PORT=8080
   HEALTH_CHECK_TIMEOUT=10
   PROXY_TIMEOUT=30
   FAILOVER_THRESHOLD_MS=3000
   FAILOVER_FAILURE_COUNT=3
   ```
3. Run the pre-flight diagnostic tool:
   ```bash
   python test_cloud_connection.py
   ```
4. Start the Proxy Balancer and DR Monitoring Daemon:
   ```bash
   # Terminal 1: Proxy Router
   python proxy_server.py

   # Terminal 2: Telemetry & Failover Daemon
   python monitoring_daemon.py
   ```
5. Navigate to `http://localhost:8080` to access the live application.

---

## Option 2: Deploying New Cloud Instances from Scratch

We have provided two automated, containerized deployment scripts that build and deploy production Docker containers directly to AWS and Azure:

### 1. Deploying the AWS Node (AWS App Runner)
AWS App Runner provides a fully-managed container runtime with automatic HTTPS certificates, health probes, and auto-scaling.

1. Configure your AWS credentials:
   ```bash
   aws configure
   ```
2. Run the deployment script:
   ```bash
   ./deploy/deploy_aws.sh
   ```
3. The script will:
   - Create an Amazon ECR container repository (`novapay-app`).
   - Build and push the production container image.
   - Provision an AWS App Runner service with production environment variables (`PRIMARY_CLOUD=aws`, `DATABASE_URL`, `PORT=8080`).
   - Configure health check probes at `/health`.
   - Output the generated public HTTPS URL.

### 2. Deploying the Azure Node (Azure App Service Linux Container)
Azure App Service Web Apps for Containers provides high-availability Linux container hosting with SSL.

1. Log in to your Azure account:
   ```bash
   az login
   ```
2. Run the deployment script:
   ```bash
   ./deploy/deploy_azure.sh
   ```
3. The script will:
   - Create an Azure Resource Group (`novapay-rg`).
   - Create an Azure Container Registry (ACR) and build the container image in the cloud.
   - Create an Azure App Service Plan (Linux) and Web App.
   - Configure environment variables (`PRIMARY_CLOUD=azure`, `WEBSITES_PORT=5000`, `DATABASE_URL`).
   - Configure health check probes at `/health`.
   - Output the generated public HTTPS URL (`https://<app-name>.azurewebsites.net`).

---

## 🔍 Pre-Flight Diagnostic Tool

Use `test_cloud_connection.py` to audit your setup before directing real user traffic:
```bash
python test_cloud_connection.py
```
This utility checks:
- **AWS Health Endpoint**: Status, round-trip latency, CPU/memory telemetry, database health.
- **Azure Health Endpoint**: Status, round-trip latency, CPU/memory telemetry, database health.
- **Proxy Status**: Active routing destination, upstream reachability.
- **Database Connection**: Direct PostgreSQL connection to Supabase pooler.

---

## 🛡️ Testing Disaster Recovery Failover

1. Log in to the NovaPay Admin Console:
   - **URL:** `http://localhost:8080/admin/monitoring`
   - **Admin User:** `admin@novapay.co.uk` / `Admin@Nova2025!`
2. **Observe Telemetry:** The gauges will display live real-time latency and metrics streamed from your real AWS and Azure hosts.
3. **Simulate Outage:**
   - Temporarily pause or stop the AWS instance in the AWS Management Console, or trigger a manual failover from the UI.
4. **Observe Automated Recovery:**
   - Within 3 failures (or if latency exceeds 3000ms), the Telemetry Daemon signals the Proxy to route all traffic to Azure.
   - RTO (Recovery Time Objective) is calculated and saved to the database.
   - An alert notification is delivered to admins.
   - Refreshing the banking app will seamlessly serve pages from Azure.
