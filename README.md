# NovaPay: Intelligent Multi-Cloud Banking & Disaster Recovery System

### Academic Context
* **Project Title:** Design and Evaluation of an Intelligent Multi-Cloud Disaster Recovery System with Real-Time Monitoring and Automated Failover
* **Student:** Ankit Kumar (ID: KUM24233914)
* **Degree:** MSc Computer Science, UCB (University College Birmingham)
* **Module:** 2220

---

## 🏦 Overview
NovaPay is a high-fidelity retail digital banking application simulated in a multi-cloud configuration (AWS + Azure). It implements an active-passive disaster recovery (DR) pattern with a lightweight proxy load balancer and a telemetry monitoring daemon. 

### Key Features
1. **Core Banking Engine:** Checking, Savings, and tax-free Cash ISA accounts, real-time transaction ledgers, virtual debit card issuance, and automated beneficiary registries.
2. **Disaster Recovery (DR) Telemetry:** Automated active-passive failover checks with less than 3-second Recovery Time Objective (RTO) triggers, consecutive error limits, and latency rolling averages.
3. **Budget & Goals Tracker:** Interactive progress widgets displaying monthly category budgets and savings goals.
4. **Command Palette (Ctrl+K):** A full-screen keyboard-navigable command search bar for routes and accounts.
5. **Interactive Aesthetics:** Rich animations, balance shimmer card glares, number counter rolls, and custom toast alerts.

---

## 🛠️ Local Installation & Run Guide (VSCode)

Follow these steps to run the complete simulated system on your machine:

### 1. Prerequisites
Ensure you have **Python 3.11+** installed.

### 2. Scaffold Virtual Environment & Install Packages
Open your terminal in VSCode and run:
```powershell
# Create venv
python -m venv venv

# Activate venv (Windows)
.\venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 3. Setup Supabase PostgreSQL Database Schema
1. Create a free project in [Supabase](https://supabase.com).
2. Go to the **SQL Editor** in the Supabase Dashboard.
3. Open a new query, copy the contents of `init.sql`, and click **Run**. This will build all 13 tables, constraints, and indexes.

### 4. Configure Environment Variables
Create a `.env` file in the project root directory and add your Supabase credentials:
```env
SECRET_KEY=novapay_secret_session_key_32_chars_long
FLASK_ENV=development
PORT=5000

# Supabase API URLs
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# Direct connection URI string
DATABASE_URL=postgresql://postgres:[password]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
```

### 5. Seed Mock Data
Inject the default admin and high-fidelity mock users with 6 months of transaction histories:
```bash
python seed_data.py
```

### 6. Run the Multi-Cloud Local Cluster
To simulate the DR cluster, you will need to open **four** separate terminal windows in VSCode:

* **Terminal 1 (AWS PrimaryBanking Node):**
  ```bash
  python run.py --aws
  ```
  *(Starts on port 5001)*

* **Terminal 2 (Azure PassiveBanking Node):**
  ```bash
  python run.py --azure
  ```
  *(Starts on port 5002)*

* **Terminal 3 (Traffic Proxy load balancer):**
  ```bash
  python proxy_server.py
  ```
  *(Starts on port 8080)*

* **Terminal 4 (Disaster Recovery Telemetry Daemon):**
  ```bash
  python monitoring_daemon.py
  ```
  *(Monitors nodes every 30s and handles failover routing shifts)*

Open your browser and navigate to: **`http://localhost:8080`**

---

## ☁️ Real-Time Multi-Cloud Deployment (AWS & Azure Live Hosts)

NovaPay can connect directly to real, live cloud hosts on **Amazon Web Services (AWS)** and **Microsoft Azure**.

### 1. Pre-Flight Diagnostic Check
Verify your current cloud node reachability, latency, proxy status, and database connection:
```bash
python test_cloud_connection.py
```

### 2. Connect to Existing Cloud Hosts
If you already have running instances or domains on AWS and Azure:
1. Open `.env` and set your real cloud HTTPS URLs:
   ```env
   AWS_URL=https://novapay-aws.your-app-runner-url.awsapprunner.com
   AZURE_URL=https://novapay-azure.azurewebsites.net
   PRIMARY_CLOUD=aws
   ```
2. Start the Proxy Balancer and DR Daemon:
   ```bash
   python proxy_server.py
   python monitoring_daemon.py
   ```

### 3. Automated Cloud Deployment Scripts
To deploy the application to AWS and Azure from your machine:
* **Deploy to AWS (App Runner & ECR):**
  ```bash
  ./deploy/deploy_aws.sh
  ```
* **Deploy to Azure (App Service Linux Container & ACR):**
  ```bash
  ./deploy/deploy_azure.sh
  ```
See [deploy/README.md](deploy/README.md) for full cloud configuration details.

---

## 🧪 Testing Disaster Recovery Failover

1. Log in with admin credentials:
   * **Email:** `admin@novapay.co.uk`
   * **Password:** `Admin@Nova2025!`
2. Navigate to **`http://localhost:8080/admin/monitoring`** to view the live node telemetry gauges.
3. **Simulate Outage:** Go to **Terminal 1** (AWS Banking Node) and press `Ctrl+C` to terminate the process (or stop the AWS instance).
4. **Observe recovery:**
   * Within 30 seconds, the Telemetry Daemon will log 3 consecutive failures for AWS.
   * It will signal the Proxy Server to point to Azure (`:5002` or live Azure URL) and log RTO stats.
   * An administrative alert notification will be broadcast to the database.
   * Refresh the bank pages; traffic will be successfully answered by the Azure node.
