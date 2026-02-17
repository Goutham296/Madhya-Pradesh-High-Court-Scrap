import time
import os
import re
import io
# Flask is the web framework used to create the API
from flask import Flask, request, jsonify, send_file
# Selenium is used for browser automation (navigating the website)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
# FPDF is used to generate PDF files
from fpdf import FPDF
# BeautifulSoup is used to parse HTML content
from bs4 import BeautifulSoup
# Pytesseract and Pillow (PIL) are used for OCR (Optical Character Recognition) to solve CAPTCHAs
import pytesseract
from PIL import Image

# Auto-configure Tesseract Path for macOS (Homebrew)
# This prevents "tesseract not found" errors if it's not in the PATH
tesseract_paths = [
    '/opt/homebrew/bin/tesseract', # Apple Silicon
    '/usr/local/bin/tesseract'     # Intel Mac
]
for path in tesseract_paths:
    if os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        print(f"Tesseract found at: {path}")
        break

app = Flask(__name__)

# Custom PDF class extending FPDF to add headers and footers
class PDFReport(FPDF):
    def header(self):
        # Set font for the header: Arial, Bold, size 12
        self.set_font('Arial', 'B', 12)
        # Title centered
        self.cell(0, 10, 'eCourts Case Status Report', 0, 1, 'C')
        # Line break
        self.ln(10)

    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        # Page number
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def scrape_ecourts(case_type_text, case_number, year):
    """Main function to automate the browser and scrape case details."""
    # Setup Chrome options to configure how the browser behaves
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # Commented out so you can see the browser and enter CAPTCHA
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')
    
    # Initialize the Chrome driver using WebDriver Manager to auto-download the correct driver version
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        # 1. Navigate to the URL
        url = "https://hcservices.ecourts.gov.in/ecourtindiaHC/cases/case_no.php?state_cd=7&dist_cd=1&court_code=1&stateNm=Madhya%20Pradesh"
        driver.get(url)
        time.sleep(2) # Pause to allow page scripts/styles to initialize
        
        # Create a WebDriverWait object to wait for elements to appear (up to 20 seconds)
        wait = WebDriverWait(driver, 20)

        # 2. Select Case Type
        # Note: We need to find the select element. The ID usually resembles 'case_type' or similar.
        # Since IDs are dynamic in some PHP apps, we might need to adjust this selector based on inspection.
        print("Selecting Case Type...")
        case_type_select = Select(wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "select[id='case_type'], select[name='case_type']"))))
        
        # Wait for dropdown options to populate (eCourts loads them dynamically via AJAX)
        for _ in range(10):
            if len(case_type_select.options) > 1: break
            time.sleep(0.5)
        
        # We try to select by visible text (e.g., "Cr.A(SJ) - CRIMINAL APPEAL...")
        # If the exact text doesn't match, we might need to iterate options to find a partial match.
        found = False
        for option in case_type_select.options:
            if case_type_text in option.text:
                case_type_select.select_by_visible_text(option.text)
                found = True
                break
        
        if not found:
            print(f"Case type '{case_type_text}' not found. Keeping browser open for 60s for debugging.")
            time.sleep(60)
            return {"error": f"Case type '{case_type_text}' not found in dropdown."}
        
        # Allow time for any AJAX fields (like case number input) to enable/appear after selection
        time.sleep(3)

        # 3. Enter Case Number
        print("Entering Case Number...")
        # Wait for the input field to be visible
        case_num_input = wait.until(EC.visibility_of_element_located((
            By.CSS_SELECTOR, 
            "input[id='search_case_no'], input[name='search_case_no']"
        )))
        case_num_input.clear()
        case_num_input.send_keys(case_number)

        # 4. Enter Year
        print("Entering Year...")
        year_input = wait.until(EC.visibility_of_element_located((
            By.CSS_SELECTOR, 
            "input[id='rgyear'], input[name='rgyear']"
        )))
        year_input.clear()
        year_input.send_keys(year)

        # 5. CAPTCHA Handling
        print("Attempting Auto-CAPTCHA...")
        captcha_solved = False
        max_attempts = 5

        # Loop to try solving CAPTCHA multiple times if it fails
        for attempt in range(max_attempts):
            if attempt > 0:
                print(f"Retrying CAPTCHA (Attempt {attempt + 1}/{max_attempts})...")
                try:
                    # Try to refresh CAPTCHA if retrying
                    refresh_btn = driver.find_element(By.CSS_SELECTOR, "img[alt='Refresh'], a[title='Refresh'], img[src*='refresh'], img[onclick*='captcha'], a[onclick*='captcha']")
                    refresh_btn.click()
                    time.sleep(2)
                except Exception as e:
                    print(f"Could not refresh CAPTCHA: {e}")

            try:
                # Locate CAPTCHA elements
                captcha_img = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "img[id='captcha_image']")))

                # Ensure the image is fully loaded in the browser before attempting OCR
                if not driver.execute_script("return arguments[0].complete && arguments[0].naturalWidth > 0", captcha_img):
                    print("CAPTCHA image not loaded properly. Retrying...")
                    continue

                captcha_input = driver.find_element(By.CSS_SELECTOR, "input[id='captcha'], input[name='captcha']")
                
                # Capture and OCR
                captcha_path = "temp_captcha.png"
                captcha_img.screenshot(captcha_path)
                
                # Requires Tesseract installed on system
                # Convert image to grayscale ('L') for better OCR accuracy
                ocr_text = pytesseract.image_to_string(Image.open(captcha_path).convert('L')).strip()
                # Remove non-alphanumeric characters
                clean_text = re.sub(r'[^a-zA-Z0-9]', '', ocr_text)
                if os.path.exists(captcha_path):
                    os.remove(captcha_path)
                print(f"OCR Result: {clean_text}")
                
                if clean_text:
                    captcha_input.clear()
                    captcha_input.send_keys(clean_text)
                    
                    # Click Go/Submit
                    go_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], input[value='Go'], button[type='submit']")
                    go_btn.click()
                    
                    # Robust Validation Loop (Fail-Safe)
                    # We check if the CAPTCHA was accepted or rejected by looking for alerts or error text
                    print("Validating CAPTCHA...")
                    validation_start = time.time()
                    outcome = None
                    
                    while time.time() - validation_start < 15:
                        # 1. Check Alert
                        try:
                            # Switch to browser alert popup if it exists
                            alert = driver.switch_to.alert
                            print(f"CAPTCHA Alert: {alert.text}")
                            alert.accept()
                            outcome = "error"
                            break
                        except: pass

                        # 2. Check Page Text & Elements
                        try:
                            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                            
                            # Error Text
                            if "invalid captcha" in body_text or "wrong captcha" in body_text or "does not match" in body_text or "verification code" in body_text:
                                print("Found text-based CAPTCHA error.")
                                outcome = "error"
                                break
                            
                            # Success Elements (Result tables or history divs)
                            success_elements = driver.find_elements(By.CSS_SELECTOR, "#showList, #show_filing_details, #history_case_no, #caseHistory, .case_details_table")
                            if any(elem.is_displayed() for elem in success_elements):
                                outcome = "success"
                                break
                            
                            # Valid Search (No Records)
                            if "record not found" in body_text or "no records found" in body_text:
                                outcome = "success"
                                break
                        except: pass
                        
                        time.sleep(0.5)
                    
                    if outcome == "success":
                        print("CAPTCHA accepted.")
                        captcha_solved = True
                        break
                    else:
                        print("Validation failed or timed out. Retrying...")
                        continue
                else:
                    print("OCR returned empty text. Retrying...")
                    continue
                    
            except Exception as e:
                print(f"Auto-CAPTCHA Error: {e}")
            
        if not captcha_solved:
            print(">>> ACTION REQUIRED: Please solve the CAPTCHA in the browser window manually.")
        
        print("Waiting up to 5 minutes for results to appear...")
        
        # Wait for the user to click the 'Go' or 'Submit' button and for results to load.
        # We assume the result table has a specific ID or Class. 
        # Adjust 'report_table' to the actual ID of the results table/div.
        # We increase timeout to 300s (5 mins) in case manual intervention is needed
        WebDriverWait(driver, 300).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#showList, #show_filing_details, #history_case_no, #caseHistory"))) 
        
        print("Results loaded. Checking for 'View' link to expand details...")

        # Attempt to click 'View' to get full details
        try:
            time.sleep(1) # Stabilize
            view_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "View")
            
            # Find the first visible 'View' link
            target_link = next((link for link in view_links if link.is_displayed()), None)
            
            if target_link:
                print("Clicking 'View' link...")
                # Use JavaScript click for reliability (avoids element interception errors)
                driver.execute_script("arguments[0].click();", target_link)
                
                print("Waiting for details to load...")
                time.sleep(2) # Allow AJAX to start
                wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#caseHistory, #history_case_no, .case_details_table")))
        except Exception as e:
            print(f"Note: Could not click 'View' or details already visible. Proceeding to scrape. ({e})")

        # 6. Scrape Data
        # This is a generic scraper for the result table. 
        # We grab the text content of the result container.
        try:
            # Target #secondpage which contains the full AJAX loaded details
            result_element = driver.find_element(By.CSS_SELECTOR, "#secondpage, #caseHistory, #history_case_no")
        except:
            # Fallback if the detailed view isn't found
            result_element = driver.find_element(By.CSS_SELECTOR, "#showList, #show_filing_details")
        
        scraped_data = {
            "text": result_element.text,
            "html": result_element.get_attribute('outerHTML')
        }
        
        return {"status": "success", "data": scraped_data}

    except Exception as e:
        # Debugging: Screenshot and Source
        
        # Print available inputs to console for debugging
        print("--- Available Input IDs on Page ---")
        try:
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for i in inputs:
                print(f"ID: {i.get_attribute('id')} | Name: {i.get_attribute('name')} | Type: {i.get_attribute('type')}")
        except:
            print("Could not list inputs.")
        print("-----------------------------------")

        print(f"Error occurred: {e}. Browser closing in 20 seconds...")
        time.sleep(20)
        return {"status": "error", "message": str(e)}
    finally:
        driver.quit()

def parse_html_data(html_content):
    """Analyzes the HTML using BeautifulSoup to extract structured data."""
    soup = BeautifulSoup(html_content, 'html.parser')
    parsed_data = {}

    # Helper to clean whitespace and non-breaking spaces
    def clean_text(text):
        return text.replace(u'\xa0', ' ').strip() if text else ""

    # --- Case Details ---
    # We look for labels like "Case Type" and extract the text next to them
    case_details = {}
    ct_label = soup.find("label", string=re.compile("Case Type"))
    if ct_label:
        row = ct_label.find_parent("span", class_="case_details_table")
        if row:
            text = row.get_text(separator=" ", strip=True)
            if ":" in text:
                case_details["Case Type"] = text.split(":", 1)[1].strip()

    fn_label = soup.find("label", string=re.compile("Filing Number"))
    if fn_label:
        row = fn_label.find_parent("span", class_="case_details_table")
        if row:
            # Regex to separate Filing Number and Filing Date if they appear in the same string
            full_text = row.get_text(separator=" ", strip=True)
            m = re.search(r"Filing Number\s*:\s*(.*?)\s*Filing Date\s*:\s*(.*)", full_text, re.IGNORECASE)
            if m:
                case_details["Filing Number"] = m.group(1).strip()
                case_details["Filing Date"] = m.group(2).strip()
            else:
                case_details["Filing Details"] = full_text

    rn_label = soup.find("label", string=re.compile("Registration Number"))
    if rn_label:
        row = rn_label.find_parent("span", class_="case_details_table")
        if row:
            full_text = row.get_text(separator=" ", strip=True)
            m = re.search(r"Registration Number\s*:\s*(.*?)\s*Registration Date\s*:\s*(.*)", full_text, re.IGNORECASE)
            if m:
                case_details["Registration Number"] = m.group(1).strip()
                case_details["Registration Date"] = m.group(2).strip()
            else:
                case_details["Registration Details"] = full_text

    cnr_label = soup.find("label", string=re.compile("CNR Number"))
    if cnr_label:
        row = cnr_label.find_parent("span", class_="case_details_table")
        if row:
            text = row.get_text(separator=" ", strip=True)
            if ":" in text:
                case_details["CNR Number"] = text.split(":", 1)[1].strip()
    
    parsed_data["Case Details"] = case_details

    # --- Status Fields ---
    case_status = {}
    # Status is often in a highlighted div (yellowish background)
    status_div = soup.find("div", style=lambda s: s and "background-color:#FBF6D9" in s)
    if status_div:
        labels = status_div.find_all("label")
        for lbl in labels:
            strongs = lbl.find_all("strong")
            if len(strongs) >= 2:
                key = clean_text(strongs[0].get_text())
                val = clean_text(strongs[1].get_text()).lstrip(":").strip()
                case_status[key] = val
    parsed_data["Case Status"] = case_status

    # --- Petitioner and Advocate ---
    pet_elem = soup.find("span", class_="Petitioner_Advocate_table")
    if pet_elem:
        parsed_data["Petitioner and Advocate"] = clean_text(pet_elem.get_text(separator="\n", strip=True))

    # --- Respondent and Advocate ---
    res_elem = soup.find("span", class_="Respondent_Advocate_table")
    if res_elem:
        parsed_data["Respondent and Advocate"] = clean_text(res_elem.get_text(separator="\n", strip=True))

    # --- Acts ---
    # Extracting data from the Acts table
    acts_data = []
    acts_table = soup.find("table", class_="Acts_table")
    if acts_table:
        headers = [th.get_text(strip=True) for th in acts_table.find_all("th")]
        for tr in acts_table.find_all("tr")[1:]:
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cols) == len(headers):
                acts_data.append(dict(zip(headers, cols)))
    parsed_data["Acts"] = acts_data

    # --- Subordinate Court Information ---
    sub_court_data = {}
    sub_court_elem = soup.find("span", class_="Lower_court_table")
    if sub_court_elem:
        keys = sub_court_elem.find_all("span", style=lambda s: s and "width:150px" in s)
        for k in keys:
            key_text = clean_text(k.get_text())
            v_label = k.find_next_sibling("label")
            if v_label:
                val_text = clean_text(v_label.get_text()).lstrip(":").strip()
                sub_court_data[key_text] = val_text
    parsed_data["Subordinate Court Information"] = sub_court_data

    # --- FIR Details ---
    fir_data = []
    # FIR details might be in a table or a span depending on the specific court page
    fir_table = soup.find("table", class_="FIR_details_table")
    if fir_table:
        headers = [th.get_text(strip=True) for th in fir_table.find_all("th")]
        rows = fir_table.find_all("tr")
        # If no th headers, try first row tds (fallback)
        if not headers and rows:
            headers = [td.get_text(strip=True) for td in rows[0].find_all("td")]
        
        if headers:
            for tr in rows[1:]:
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cols) == len(headers):
                    fir_data.append(dict(zip(headers, cols)))
    else:
        # Check for span format (common in some high courts)
        fir_span = soup.find("span", class_="FIR_details_table")
        if fir_span:
            fir_info = {}
            keys = fir_span.find_all("span", style=lambda s: s and "width:150px" in s)
            for k in keys:
                key_text = clean_text(k.get_text())
                v_label = k.find_next_sibling("label")
                if v_label:
                    val_text = clean_text(v_label.get_text()).lstrip(":").strip()
                    fir_info[key_text] = val_text
            if fir_info:
                fir_data.append(fir_info)

    if fir_data:
        parsed_data["FIR Details"] = fir_data

    # --- IA Details ---
    ia_data = []
    ia_table = soup.find("table", class_="IAheading")
    if ia_table:
        headers = [th.get_text(strip=True) for th in ia_table.find_all("th")]
        for tr in ia_table.find_all("tr")[1:]:
            cols = [td.get_text(separator=" ", strip=True) for td in tr.find_all("td")]
            if len(cols) == len(headers):
                ia_data.append(dict(zip(headers, cols)))
    parsed_data["IA Details"] = ia_data

    # --- Orders ---
    orders_data = []
    order_table = soup.find("table", class_="order_table")
    if order_table:
        header_tr = order_table.find("tr")
        if header_tr:
            headers = [td.get_text(strip=True) for td in header_tr.find_all("td")]
            for tr in order_table.find_all("tr")[1:]:
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cols) == len(headers):
                    orders_data.append(dict(zip(headers, cols)))
    parsed_data["Orders"] = orders_data

    # --- Category Details ---
    cat_data = {}
    cat_header = soup.find("h2", string=re.compile("Category Details"))
    if cat_header:
        header_table = cat_header.find_parent("table")
        if header_table:
            data_table = header_table.find_next_sibling("table")
            if data_table:
                for tr in data_table.find_all("tr"):
                    cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if len(cols) >= 2:
                        cat_data[cols[0]] = cols[1]
    parsed_data["Category Details"] = cat_data

    return parsed_data

def create_pdf(data):
    """Generates a PDF report from the parsed dictionary data."""
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Effective page width (A4 is 210mm, margins default 10mm -> 190mm)
    page_width = 190 
    
    if isinstance(data, dict):
        for section, content in data.items():
            # Check for page break before starting a new section
            if pdf.get_y() > 250:
                pdf.add_page()

            # Section Header (Blue background)
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(200, 220, 255)
            pdf.cell(0, 8, section, 1, 1, 'L', fill=True)
            
            pdf.set_font("Arial", size=10)
            
            if isinstance(content, dict):
                # Key-Value Table (e.g., Case Details)
                w_key = 60
                w_val = page_width - w_key
                
                for k, v in content.items():
                    # Encode text to latin-1 to avoid FPDF unicode errors
                    safe_k = str(k).encode('latin-1', 'replace').decode('latin-1')
                    safe_v = str(v).encode('latin-1', 'replace').decode('latin-1')
                    
                    # Check page break
                    if pdf.get_y() > 260:
                        pdf.add_page()
                    
                    x_start = pdf.get_x()
                    y_start = pdf.get_y()
                    
                    # Print Key
                    pdf.set_font("Arial", 'B', 10)
                    pdf.multi_cell(w_key, 6, safe_k, 0, 'L')
                    y_end_k = pdf.get_y()
                    
                    # Print Value
                    pdf.set_xy(x_start + w_key, y_start)
                    pdf.set_font("Arial", size=10)
                    pdf.multi_cell(w_val, 6, safe_v, 0, 'L')
                    y_end_v = pdf.get_y()
                    
                    # Calculate Row Height based on the tallest cell
                    row_height = max(y_end_k - y_start, y_end_v - y_start)
                    
                    # Draw Borders
                    pdf.rect(x_start, y_start, w_key, row_height)
                    pdf.rect(x_start + w_key, y_start, w_val, row_height)
                    
                    # Move to next row
                    pdf.set_xy(x_start, y_start + row_height)
            
            elif isinstance(content, list):
                # List of dictionaries (Tables like Orders, Acts)
                if not content:
                    pdf.cell(0, 6, "No records found.", 1, 1)
                else:
                    # Determine headers
                    headers = list(content[0].keys())
                    num_cols = len(headers)
                    if num_cols > 0:
                        col_width = page_width / num_cols
                        
                        # Header Row
                        pdf.set_font("Arial", 'B', 10)
                        pdf.set_fill_color(240, 240, 240)
                        
                        # Check page break
                        if pdf.get_y() > 260:
                            pdf.add_page()

                        x_start = pdf.get_x()
                        y_start = pdf.get_y()
                        
                        # Print Headers
                        max_h = 0
                        ys = []
                        for i, h in enumerate(headers):
                            safe_h = str(h).encode('latin-1', 'replace').decode('latin-1')
                            pdf.set_xy(x_start + (i * col_width), y_start)
                            pdf.multi_cell(col_width, 6, safe_h, 0, 'C', fill=True)
                            ys.append(pdf.get_y())
                        
                        row_height = max(ys) - y_start
                        # Draw borders for header
                        for i in range(num_cols):
                            pdf.rect(x_start + (i * col_width), y_start, col_width, row_height)
                        
                        pdf.set_xy(x_start, y_start + row_height)
                        
                        # Data Rows
                        pdf.set_font("Arial", size=9)
                        for row in content:
                            # Check page break
                            if pdf.get_y() > 260:
                                pdf.add_page()
                            
                            y_start = pdf.get_y()
                            x_start = pdf.get_x()
                            
                            ys = []
                            for i, h in enumerate(headers):
                                val = row.get(h, "")
                                safe_val = str(val).encode('latin-1', 'replace').decode('latin-1')
                                pdf.set_xy(x_start + (i * col_width), y_start)
                                pdf.multi_cell(col_width, 6, safe_val, 0, 'L')
                                ys.append(pdf.get_y())
                            
                            row_height = max(ys) - y_start
                            # Draw borders
                            for i in range(num_cols):
                                pdf.rect(x_start + (i * col_width), y_start, col_width, row_height)
                            
                            pdf.set_xy(x_start, y_start + row_height)

            elif isinstance(content, str):
                # Raw text block
                safe_text = content.encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 6, safe_text, 1)
            
            pdf.ln(5)
    else:
        # Fallback for Raw Text
        safe_text = data.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, safe_text)
    
    # Return PDF as bytes (in-memory) instead of saving to file
    return io.BytesIO(pdf.output(dest='S').encode('latin-1'))

@app.route('/scrape-case', methods=['POST'])
def handle_scrape_request():
    """API Endpoint to receive scrape requests."""
    req_data = request.get_json()
    
    case_type = req_data.get('case_type')
    case_number = req_data.get('case_number')
    year = req_data.get('year')
    
    # Validate input
    if not all([case_type, case_number, year]):
        return jsonify({"error": "Missing required fields"}), 400
    
    print(f"Processing: {case_type} / {case_number} / {year}")
    
    # 1. Scrape
    result = scrape_ecourts(case_type, case_number, year)

    if result.get("status") == "error":
        return jsonify(result), 500
    
    if "error" in result:
        return jsonify(result), 400

    data = result['data']

    # HTML saving removed to keep directory clean
    # (The data is parsed directly from memory below)

    # Parse HTML for structured PDF
    parsed_data = parse_html_data(data['html'])
    print("Analyzed Data:", parsed_data)

    # 2. Generate PDF
    pdf_filename = f"Case_{case_number}_{year}.pdf"
    pdf_stream = create_pdf(parsed_data)
    
    # 3. Return PDF
    return send_file(pdf_stream, as_attachment=True, download_name=pdf_filename, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
