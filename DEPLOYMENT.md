# 🚀 DayPlan — Deployment Guide (Streamlit Community Cloud)

This guide provides step-by-step instructions for deploying **DayPlan** to **Streamlit Community Cloud**, free of charge, with zero external API keys or server costs.

---

## 📋 Prerequisites

Before deploying, ensure you have:
1. A **GitHub account** ([github.com](https://github.com)).
2. A **Streamlit Community Cloud account** ([share.streamlit.io](https://share.streamlit.io)) connected to your GitHub account.
3. Git installed on your computer.

---

## Step 1: Initialize Git and Prepare Local Repository

If you have not already initialized Git in your local `DayPlan` folder, run these commands in your terminal:

```bash
cd /Users/hgouthamgoud/Desktop/DayPlan

# Initialize git repository
git init

# Check the files that will be added (verify .venv and cache files are ignored)
git status

# Stage all project files
git add .

# Create the initial commit
git commit -m "feat: initial commit of DayPlan MVP with adaptive rescheduling engine"
```

---

## Step 2: Create a Remote Repository on GitHub

1. Open your web browser and navigate to **[github.com/new](https://github.com/new)**.
2. In the **Repository name** field, enter: `DayPlan` (or `dayplan-agent`).
3. Set the visibility to **Public** (required for free Streamlit Community Cloud hosting).
4. **Do NOT** initialize with a README, .gitignore, or license (we already created them locally).
5. Click **Create repository**.

---

## Step 3: Push Your Code to GitHub

Copy the repository URL shown on GitHub (e.g. `https://github.com/<YOUR-USERNAME>/DayPlan.git`), then run:

```bash
# Rename the default branch to main
git branch -M main

# Link your local repo to GitHub (replace <YOUR-USERNAME> with your actual GitHub username)
git remote add origin https://github.com/<YOUR-USERNAME>/DayPlan.git

# Push code to GitHub
git push -u origin main
```

---

## Step 4: Deploy on Streamlit Community Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and log in with your GitHub account.
2. Click the **"New app"** (or **"Create app"**) button in the top right corner.
3. Fill in the deployment details:
   - **Repository:** `<YOUR-USERNAME>/DayPlan`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL (optional):** Choose a custom subdomain (e.g., `dayplan-planner.streamlit.app`).
4. Click **Deploy!**

---

## Step 5: Verification & Post-Deployment Check

Streamlit Cloud will provision a container, install dependencies from `requirements.txt`, and launch `app.py`.

Once the app opens:
1. Verify that the **Dashboard** metrics render without errors.
2. Click **"Load Selected Scenario"** from the left sidebar to test a preset (e.g. *Missed Morning Task*).
3. Test the **"Replan My Day Now"** button to confirm the rescheduling engine functions properly.
4. Go to **"Data Backup & Restore"** and download a test JSON backup.

---

## Step 6: Updating Your Deployed App

Whenever you make improvements or add new features in the future, updating the live app is as simple as pushing to GitHub:

```bash
# Stage changed files
git add .

# Commit your changes
git commit -m "feat: improve scheduling heuristics"

# Push to GitHub
git push origin main
```

Streamlit Community Cloud automatically detects the new commit on `main` and redeploys the app within seconds!

---

## 🛠️ Troubleshooting Common Deployment Issues

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| **`ModuleNotFoundError: No module named 'dayplan'`** | Python cannot find package root when running `pytest` or `app.py`. | In `app.py`, imports are relative to the root (`dayplan.planner`). Streamlit runs from the repo root where `dayplan/` resides. In `pytest.ini`, `pythonpath = .` ensures tests discover the package. |
| **`File not found: requirements.txt`** | File missing or misspelled. | Ensure `requirements.txt` is in the root directory alongside `app.py`. |
| **Data disappears after tab reload** | Normal browser session isolation behavior. | The MVP uses `st.session_state` to prevent user tasks from being stored on a shared public server. Use the **Data Backup** tab to download your JSON file before closing your session. |
| **App takes >2 minutes to wake up** | Streamlit Cloud free instances sleep when idle. | This is standard for free tier hosting. Clicking the app will wake the container. |
