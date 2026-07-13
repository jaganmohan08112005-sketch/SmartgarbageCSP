# 🗑️ SmartGarbage: Predictive Municipal Waste Management Platform

SmartGarbage is an end-to-end, data-driven web platform designed to optimize municipal waste disposal tracking, predict route failures, and streamline civic complaint management. The system leverages a **Flask App Factory** backend, an integrated **SQLite database**, and a **Scikit-Learn Random Forest Classifier** trained on real community field metrics to anticipate missed collection risks across regional wards.

---# 🗑️ SmartGarbage: Predictive Municipal Waste Management Platform

SmartGarbage is an end-to-end, data-driven web platform designed to optimize municipal waste disposal tracking, predict route failures, and streamline civic complaint management. The system leverages a **Flask App Factory** backend, an integrated **SQLite database**, and a **Scikit-Learn Random Forest Classifier** trained on real community field metrics to anticipate missed collection risks across regional wards.

---

## 📁 Project Architecture

The workspace is organized into a highly scalable, decoupled file structure:

```text
SmartGarbage/
├── app/
│   ├── __init__.py         # Flask Application Factory & DB initialization
│   ├── models.py           # SQLAlchemy SQLite Database schemas
│   ├── routes.py           # Central URL blueprints and form controllers
│   ├── ml_model.py         # Runtime predictive inference engine
│   ├── ml_model.pkl        # Trained Random Forest model binary matrix
│   ├── static/             # Assets and custom global stylesheets
│   │   ├── style.css       # Core UI styles
│   │   ├── survey_chart.png# Compiled data analysis visual asset
│   │   └── uploads/        # Stored citizen image proof attachments
│   └── templates/          # Jinja2 HTML layout views
│       ├── base.html       # Shared global Bootstrap 5 navbar wrapper
│       ├── index.html      # Central interactive analytics dashboard
│       ├── schedule.html   # Ward timetable view & ML alert interface
│       ├── report.html     # Multi-part citizen ticket reporting form
│       ├── success.html    # Submission confirmation greeting layout
│       └── admin.html      # Administrative dispatch management portal
├── requirements.txt        # Backend package dependency registry
├── run.py                  # Primary application entry execution gateway
├── train_model.py          # Machine learning model compilation pipeline
├── seed_db.py              # SQLite mock timetable populator script
├── analyze_survey.py       # Automated survey chart generation tool
└── survey_responses.csv    # Exported civic Google Form dataset
```

---

## 🚀 Step-by-Step Execution Guide

Follow these sequential steps in **Windows PowerShell** to activate, initialize, and test the entire software ecosystem:

### 1. Environment Setup & Installation
Ensure you are in the project root directory, then run the dependency installer:
```powershell
cd C:\Users\chand\SmartGarbage
pip install -r requirements.txt
```

### 2. Compile the Predictive Engine
Execute the training script to ingest your survey responses and generate the production model binary file:
```powershell
python train_model.py
```
*Output Verification:* Look for `Model saved to app/ml_model.pkl`.

### 3. Initialize & Seed the Database Tables
Generate the database schema and inject default garbage collection timetables for Wards 1, 2, and 3:
```powershell
python seed_db.py
```
*Output Verification:* Look for `🎉 Database successfully seeded with 8 active collection schedules!`.

### 4. Build Project Validation Analytics
Generate the visualization charts from your citizen data files to populate the main dashboard interface:
```powershell
python analyze_survey.py
```
*Output Verification:* Look for `🎉 SUCCESS: Visual chart saved to -> app/static/survey_chart.png`.

### 5. Launch the Web Application Server
Boot up the local system network engine:
```powershell
python run.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** inside your web browser to access the active interface.

---

## 🛠️ System Capabilities & Verification Test Matrix

### 📅 Core Schedule Tunnels & ML Risk Forecasting
* **Location:** `/schedule`
* **Test Flow:** Choose **Ward 1 - Banjara Hills** or **Ward 2 - Jubilee Hills** from the interface selector dropdown.
* **Mechanism:** The system extracts active row timetables dynamically from `garbage.db`. Concurrently, the inference engine parses the current date parameters, checks historical telemetry bounds, and computes a risk factor. The frontend template switches colors immediately to deliver a custom alert window to users.

### ⚠️ Multi-Part Citizen Filing & Upload Streams
* **Location:** `/report`
* **Test Flow:** Provide test name, address data parameters, select a local sample asset image, and press submit.
* **Mechanism:** Flask handles the form streaming payload safely, processes file strings using `secure_filename` logic, and saves assets to `app/static/uploads/`. It logs a unique item index into the SQLite table and routes users seamlessly to the confirmation screen.

### 👨‍💼 Dispatcher Control & Resolution Dashboard
* **Location:** `/admin`
* **Test Flow:** Review submitted complaints, select **View Attachment** to verify images, and click **Mark Resolved**.
* **Mechanism:** The server queries all entries by date, displays relative tracking tags, and dynamically alters database state structures instantly upon user click.

---

## 📈 Data Grounding Methodology
The integrated Machine Learning algorithm does not rely on random assumptions. It uses a **Random Forest Classifier** model that is mathematically grounded in community field surveys. Feature mapping indexes include:
* **`day_of_week`**: Temporal collection window mapping.
* **`is_monsoon`**: Accounts for regional weather anomalies and seasonal route slowdowns.
* **`complaints_last7`**: Monitors rolling community complaint velocity parameters to flag active grid blockages.
* **`ward_id`**: Maps localized structural infrastructure density constraints.
# 🗑️ SmartGarbage: Predictive Municipal Waste Management Platform

SmartGarbage is an end-to-end, data-driven web platform designed to optimize municipal waste disposal tracking, predict route failures, and streamline civic complaint management. The system leverages a **Flask App Factory** backend, an integrated **SQLite database**, and a **Scikit-Learn Random Forest Classifier** trained on real community field metrics to anticipate missed collection risks across regional wards.

---

## 📁 Project Architecture

The workspace is organized into a highly scalable, decoupled file structure:

```text
SmartGarbage/
├── app/
│   ├── __init__.py         # Flask Application Factory & DB initialization
│   ├── models.py           # SQLAlchemy SQLite Database schemas
│   ├── routes.py           # Central URL blueprints and form controllers
│   ├── ml_model.py         # Runtime predictive inference engine
│   ├── ml_model.pkl        # Trained Random Forest model binary matrix
│   ├── static/             # Assets and custom global stylesheets
│   │   ├── style.css       # Core UI styles
│   │   ├── survey_chart.png# Compiled data analysis visual asset
│   │   └── uploads/        # Stored citizen image proof attachments
│   └── templates/          # Jinja2 HTML layout views
│       ├── base.html       # Shared global Bootstrap 5 navbar wrapper
│       ├── index.html      # Central interactive analytics dashboard
│       ├── schedule.html   # Ward timetable view & ML alert interface
│       ├── report.html     # Multi-part citizen ticket reporting form
│       ├── success.html    # Submission confirmation greeting layout
│       └── admin.html      # Administrative dispatch management portal
├── requirements.txt        # Backend package dependency registry
├── run.py                  # Primary application entry execution gateway
├── train_model.py          # Machine learning model compilation pipeline
├── seed_db.py              # SQLite mock timetable populator script
├── analyze_survey.py       # Automated survey chart generation tool
└── survey_responses.csv    # Exported civic Google Form dataset
```

---

## 🚀 Step-by-Step Execution Guide

Follow these sequential steps in **Windows PowerShell** to activate, initialize, and test the entire software ecosystem:

### 1. Environment Setup & Installation
Ensure you are in the project root directory, then run the dependency installer:
```powershell
cd C:\Users\chand\SmartGarbage
pip install -r requirements.txt
```

### 2. Compile the Predictive Engine
Execute the training script to ingest your survey responses and generate the production model binary file:
```powershell
python train_model.py
```
*Output Verification:* Look for `Model saved to app/ml_model.pkl`.

### 3. Initialize & Seed the Database Tables
Generate the database schema and inject default garbage collection timetables for Wards 1, 2, and 3:
```powershell
python seed_db.py
```
*Output Verification:* Look for `🎉 Database successfully seeded with 8 active collection schedules!`.

### 4. Build Project Validation Analytics
Generate the visualization charts from your citizen data files to populate the main dashboard interface:
```powershell
python analyze_survey.py
```
*Output Verification:* Look for `🎉 SUCCESS: Visual chart saved to -> app/static/survey_chart.png`.

### 5. Launch the Web Application Server
Boot up the local system network engine:
```powershell
python run.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** inside your web browser to access the active interface.

---

## 🛠️ System Capabilities & Verification Test Matrix

### 📅 Core Schedule Tunnels & ML Risk Forecasting
* **Location:** `/schedule`
* **Test Flow:** Choose **Ward 1 - Banjara Hills** or **Ward 2 - Jubilee Hills** from the interface selector dropdown.
* **Mechanism:** The system extracts active row timetables dynamically from `garbage.db`. Concurrently, the inference engine parses the current date parameters, checks historical telemetry bounds, and computes a risk factor. The frontend template switches colors immediately to deliver a custom alert window to users.

### ⚠️ Multi-Part Citizen Filing & Upload Streams
* **Location:** `/report`
* **Test Flow:** Provide test name, address data parameters, select a local sample asset image, and press submit.
* **Mechanism:** Flask handles the form streaming payload safely, processes file strings using `secure_filename` logic, and saves assets to `app/static/uploads/`. It logs a unique item index into the SQLite table and routes users seamlessly to the confirmation screen.

### 👨‍💼 Dispatcher Control & Resolution Dashboard
* **Location:** `/admin`
* **Test Flow:** Review submitted complaints, select **View Attachment** to verify images, and click **Mark Resolved**.
* **Mechanism:** The server queries all entries by date, displays relative tracking tags, and dynamically alters database state structures instantly upon user click.

---

## 📈 Data Grounding Methodology
The integrated Machine Learning algorithm does not rely on random assumptions. It uses a **Random Forest Classifier** model that is mathematically grounded in community field surveys. Feature mapping indexes include:
* **`day_of_week`**: Temporal collection window mapping.
* **`is_monsoon`**: Accounts for regional weather anomalies and seasonal route slowdowns.
* **`complaints_last7`**: Monitors rolling community complaint velocity parameters to flag active grid blockages.
* **`ward_id`**: Maps localized structural infrastructure density constraints.


## 📁 Project Architecture

The workspace is organized into a highly scalable, decoupled file structure:

```text
SmartGarbage/
├── app/
│   ├── __init__.py         # Flask Application Factory & DB initialization
│   ├── models.py           # SQLAlchemy SQLite Database schemas
│   ├── routes.py           # Central URL blueprints and form controllers
│   ├── ml_model.py         # Runtime predictive inference engine
│   ├── ml_model.pkl        # Trained Random Forest model binary matrix
│   ├── static/             # Assets and custom global stylesheets
│   │   ├── style.css       # Core UI styles
│   │   ├── survey_chart.png# Compiled data analysis visual asset
│   │   └── uploads/        # Stored citizen image proof attachments
│   └── templates/          # Jinja2 HTML layout views
│       ├── base.html       # Shared global Bootstrap 5 navbar wrapper
│       ├── index.html      # Central interactive analytics dashboard
│       ├── schedule.html   # Ward timetable view & ML alert interface
│       ├── report.html     # Multi-part citizen ticket reporting form
│       ├── success.html    # Submission confirmation greeting layout
│       └── admin.html      # Administrative dispatch management portal
├── requirements.txt        # Backend package dependency registry
├── run.py                  # Primary application entry execution gateway
├── train_model.py          # Machine learning model compilation pipeline
├── seed_db.py              # SQLite mock timetable populator script
├── analyze_survey.py       # Automated survey chart generation tool
└── survey_responses.csv    # Exported civic Google Form dataset
```

---

## 🚀 Step-by-Step Execution Guide

Follow these sequential steps in **Windows PowerShell** to activate, initialize, and test the entire software ecosystem:

### 1. Environment Setup & Installation
Ensure you are in the project root directory, then run the dependency installer:
```powershell
cd C:\Users\chand\SmartGarbage
pip install -r requirements.txt
```

### 2. Compile the Predictive Engine
Execute the training script to ingest your survey responses and generate the production model binary file:
```powershell
python train_model.py
```
*Output Verification:* Look for `Model saved to app/ml_model.pkl`.

### 3. Initialize & Seed the Database Tables
Generate the database schema and inject default garbage collection timetables for Wards 1, 2, and 3:
```powershell
python seed_db.py
```
*Output Verification:* Look for `🎉 Database successfully seeded with 8 active collection schedules!`.

### 4. Build Project Validation Analytics
Generate the visualization charts from your citizen data files to populate the main dashboard interface:
```powershell
python analyze_survey.py
```
*Output Verification:* Look for `🎉 SUCCESS: Visual chart saved to -> app/static/survey_chart.png`.

### 5. Launch the Web Application Server
Boot up the local system network engine:
```powershell
python run.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** inside your web browser to access the active interface.

---

## 🛠️ System Capabilities & Verification Test Matrix

### 📅 Core Schedule Tunnels & ML Risk Forecasting
* **Location:** `/schedule`
* **Test Flow:** Choose **Ward 1 - Banjara Hills** or **Ward 2 - Jubilee Hills** from the interface selector dropdown.
* **Mechanism:** The system extracts active row timetables dynamically from `garbage.db`. Concurrently, the inference engine parses the current date parameters, checks historical telemetry bounds, and computes a risk factor. The frontend template switches colors immediately to deliver a custom alert window to users.

### ⚠️ Multi-Part Citizen Filing & Upload Streams
* **Location:** `/report`
* **Test Flow:** Provide test name, address data parameters, select a local sample asset image, and press submit.
* **Mechanism:** Flask handles the form streaming payload safely, processes file strings using `secure_filename` logic, and saves assets to `app/static/uploads/`. It logs a unique item index into the SQLite table and routes users seamlessly to the confirmation screen.

### 👨‍💼 Dispatcher Control & Resolution Dashboard
* **Location:** `/admin`
* **Test Flow:** Review submitted complaints, select **View Attachment** to verify images, and click **Mark Resolved**.
* **Mechanism:** The server queries all entries by date, displays relative tracking tags, and dynamically alters database state structures instantly upon user click.

---

## 📈 Data Grounding Methodology
The integrated Machine Learning algorithm does not rely on random assumptions. It uses a **Random Forest Classifier** model that is mathematically grounded in community field surveys. Feature mapping indexes include:
* **`day_of_week`**: Temporal collection window mapping.
* **`is_monsoon`**: Accounts for regional weather anomalies and seasonal route slowdowns.
* **`complaints_last7`**: Monitors rolling community complaint velocity parameters to flag active grid blockages.
* **`ward_id`**: Maps localized structural infrastructure density constraints.
