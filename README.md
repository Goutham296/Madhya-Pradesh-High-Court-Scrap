# Madhya Pradesh HighCourts Case Scraper

A Flask-based web scraping application designed to retrieve case status and details from the eCourts Services website. It automates the search process, includes automatic CAPTCHA solving, and generates a structured PDF report of the case details directly in memory.

## Features
- **Automated Navigation:** Uses Selenium to fill forms and navigate the eCourts portal.
- **Automatic CAPTCHA Solving:** Uses OCR (Tesseract) to automatically solve CAPTCHAs, eliminating the need for manual entry.
- **Data Extraction:** Scrapes Case Status, Orders, FIR Details, Acts, and more.
- **PDF Generation:** Returns a formatted PDF report without creating temporary files on the server.

## Technology Stack
*   **Python 3.x** & **Flask**
*   **Selenium WebDriver** (Browser Automation)
*   **Tesseract OCR** & **Pillow** (CAPTCHA Processing)
*   **BeautifulSoup4** (HTML Parsing)
*   **FPDF** (PDF Generation)

## Installation

1.  **Prerequisites:**
    - Python 3.x
    - Google Chrome Browser
    - Tesseract OCR (installed and added to system PATH)

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Workflow & CAPTCHA Handling
1.  **Browser Launch:** The app opens a visible Chrome window.
2.  **Form Filling:** Automatically navigates and fills Case Type, Number, and Year.
3.  **CAPTCHA Solving:** The script automatically detects and solves the CAPTCHA using OCR technology.
4.  **Extraction:** Once results load, the script scrapes the data and closes the browser.

## Usage

1.  **Start the Server:**
    ```bash
    python app.py
    ```
    The server will start at `http://127.0.0.1:5000`.

2.  **Send a Request:**
    Send a POST request to the `/scrape-case` endpoint.

    **Example (cURL):**
    ```bash
    curl -X POST http://127.0.0.1:5000/scrape-case -H "Content-Type: application/json" -d '{"case_type": "Cr.A(SJ) - CRIMINAL APPEAL (SINGLE JUDGE)(24)", "case_number": "460", "year": "2006"}' --output report.pdf
    ```

## Scraped Data Points
- **Case Details:** Type, Filing/Registration No, CNR.
- **Status:** Hearing Dates, Coram, Bench.
- **Parties:** Petitioner, Respondent, Advocates.
- **Acts & FIR:** Under Acts, Police Station, FIR No.
- **Orders & IA:** Order details, Interlocutory Applications.

## Configuration
- **Target URL:** `https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php`
- **Default Scope:** Madhya Pradesh (State Code 7), District Code 1.
- *Modify `scrape_ecourts` in `app.py` to change these parameters.*
