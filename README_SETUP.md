# ECE-036 Warranty Desk — Flask Frontend

This project adds a web interface around the supplied `engine.py`. The original warranty calculations remain in `engine.py`; Flask provides the pages and form handling.

## 1. Project contents

- `engine.py` — original warranty backend
- `app.py` — Flask web application
- `data/` — supplied E014 sample CSV files and `commands.txt`
- `templates/` — HTML pages
- `static/css/style.css` — interface styling
- `static/js/app.js` — small navigation interaction
- `output/` — generated CSV reports (created automatically)

## 2. Open in VS Code

1. Extract `ECE036_Warranty_WebApp.zip`.
2. In VS Code, choose **File → Open Folder** and select `ECE036_Warranty_WebApp`.
3. Open the VS Code terminal (**Terminal → New Terminal**).
4. Create and activate a virtual environment:

### Windows PowerShell
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt:
```bat
.venv\Scripts\activate.bat
```

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
```

5. Install Flask:
```bash
python -m pip install -r requirements.txt
```

6. Start the app:
```bash
python app.py
```

7. Open this address in your browser:
```text
http://127.0.0.1:5000
```

## 3. Pages included

- Overview dashboard
- Policy register, search/filter and add policy
- Claims list and process-claim form
- Cancellation list and cancellation/refund form
- Customer directory
- CSV report downloads

## 4. Important behaviour / limitations

- At startup, the app loads the supplied `data/` files and replays `commands.txt` in its listed order through the original engine. This reproduces the sample pack's starting state.
- New policies, claims and cancellations entered through the web app are held in the Python process memory. They affect other pages during that run, but are **not permanently saved** to the original CSV inputs or a database. Download reports before stopping the server if you want to keep a snapshot of the outputs.
- Restarting the app reloads the original sample data and replays the original commands; newly entered web records are cleared.
- This is a local academic/demo application, not a production deployment. It has no authentication, database persistence, CSRF protection, or multi-user isolation.
- Do not expose the Flask development server to the public internet. Before deployment, add authentication, a database, CSRF protection, secure secret management, and production hosting.

## 5. Notes

The app uses the original `Engine` and `Policy` classes. It does not reimplement premium, coverage, claim, depreciation, deductible, replacement, or refund calculations in JavaScript.
