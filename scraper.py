from playwright.async_api import async_playwright, Page, Browser
from camoufox.async_api import AsyncCamoufox
import os
import json
import requests
from dotenv import load_dotenv
import asyncio

#.env imports
AWS_BUCKET_DATA_LOCATION = os.getenv("AWS_BUCKET_DATA_LOCATION")
AWS_BUCKET_METADATA_LOCATION = os.getenv("AWS_BUCKET_METADATA_LOCATION")

# File class definition
class File:
    def __init__(
            self,
            hbn : str,
            main_title : str, 
            session_number : str, 
            significance : str, 
            date_filed : str, 
            principal_authors : str, 
            date_read : str, 
            primary_referral : str, 
            bill_status : str,  
            text_filed : str, 
            is_file_downloadable : str
            ):
        self.hbn = hbn
        self.main_title = main_title
        self.session_number = session_number
        self.significance = significance
        self.date_filed = date_filed
        self.principal_authors = principal_authors
        self.date_read = date_read
        self.primary_referral = primary_referral
        self.bill_status = bill_status
        self.text_filed = text_filed
        self.is_file_downloadable = is_file_downloadable

    def __eq__(self, other):
        if isinstance(other, File):
            return self.hbn == other.hbn
        return False
    
    def __hash__(self):
        return hash(self.hbn)

# files set initialization
files : set[File] = set()

# JSON encoding functions
def json_encoder(obj: File):
    """
    Encodes FIle class instance to JSON instance 

    Args:
        obj (File): File object

    Raises:
        TypeError: Occurs when object passed is not an instance of the File class

    Returns:
        dict[str,str]: dictionary for JSON parsing
    """
    if isinstance(obj, File):
        return {
            'House Bill Number' : obj.hbn,
            'Main Title' : obj.main_title,
            'Session Number' : obj.session_number,
            'Significance' : obj.significance,
            'Date Filed' : obj.date_filed,
            'Principal Authors' : obj.principal_authors,
            'Date Read' : obj.date_read,
            'Primary Referral' : obj.primary_referral,
            'Bill Status' : obj.bill_status,
            'Text Filed' : obj.text_filed
        }
    raise TypeError("Object is not JSON parsable.")

def load_files_from_json(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            for item in data:
                # Reconstruct the File object using the JSON keys
                # We use .get() to avoid errors if a key is missing
                new_file = File(
                    hbn=item.get("House Bill Number"),
                    main_title=item.get("Main Title"),
                    session_number=item.get("Session Number"),
                    significance=item.get("Significance"),
                    date_filed=item.get("Date Filed"),
                    principal_authors=item.get("Principal Authors"),
                    date_read=item.get("Date Read"),
                    primary_referral=item.get("Primary Referral"),
                    bill_status=item.get("Bill Status"),
                    text_filed=item.get("Text Filed"),
                    is_file_downloadable=item.get("Downloaded", False)
                )
                files.add(new_file)
        print(f"Successfully loaded {len(files)} unique bills.")
    except FileNotFoundError:
        print("No existing JSON found. Starting with an empty set.")
        
# File download function
def download(url: str, dest_folder: str):
    """
    Downloads the file from the URL provided and places it in the destination folder provided

    Inputs:
    url (str): input URL of file
    dest_folder (str): destination folder/directory of downloaded file
    
    Outputs:
    Returns 1 if the download was successful, and 0 if not.
    """
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)  # create folder if it does not exist
    try:
        filename = url.split('/')[-1].replace(" ", "_")  
        file_path = os.path.join(dest_folder, filename)
        # print(f"URL: {url}")
        r = requests.get(url, stream=True)
        if r.ok:
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
        else:  
            return False
        return True
    except:
        return False
    
# Scraping Helper Functions
async def get_files_from_page(hb_items_locator):
    """
    Gets all house bill files from the current page

    Args:
        hb_items_locator (list[Locator]): list of scraped house bill divs

    Returns:
        None
    """
    
    count = await hb_items_locator.count()
    for i in range(count):
        hb_item = hb_items_locator.nth(i)
        
        # Trigger AOS animation
        await hb_item.scroll_into_view_if_needed()

        # Get Header Info
        hbn = await hb_item.locator("span.rounded.border span span").first.inner_text()
        main_title = await hb_item.locator("span.text-blue-500").first.inner_text()

        # Metadata Retrieval
        async def get_meta(label):
            try:
                # Logic: Find the label div, then get the very next div sibling (+)
                # only if it is inside the grid container
                value_locator = hb_item.locator(".grid.gap-1.px-5") \
                                       .locator(f"div:has-text('{label}') + div")
                
                text = await value_locator.first.inner_text(timeout=1000)
                return text.strip()
            except:
                return "N/A"

        # Check if file already exists in metadata
        if File(hbn=hbn, **dict.fromkeys(['main_title', 'session_number', 'significance', 'date_filed', 'principal_authors', 'date_read', 'primary_referral', 'bill_status', 'text_filed', 'is_file_downloadable'], "N/A")) in files:
            print(f"Skipping {hbn}: Already in database.")
            continue
        
        # PDF Link
        pdf_loc = hb_item.locator('a[href$=".pdf"]').first
        link = await pdf_loc.get_attribute('href') if await pdf_loc.count() > 0 else "N/A"
        downloadability = False
        if link != 'N/A':
            downloadability = download(link, "outputs/")
        # Build File Object

        new_file = File(
            hbn.strip(),
            main_title.strip(),
            await get_meta("Session No. :"),
            await get_meta("Significance :"),
            await get_meta("Date Filed :"),
            await get_meta("Principal Author/s :"),
            await get_meta("Date Read :"),
            await get_meta("Primary Referral :"),
            await get_meta("Bill Status :"),
            link,
            downloadability # Downloadable
        )
        files.add(new_file)
        
async def main():
    # File Scraping Progress Reset
    load_files_from_json('outputs/metadata.json')
    
    try:
        async with AsyncCamoufox(headless=False, geoip=True) as browser:
            context = await browser.new_context(viewport={"width":1000, "height":500})
            page = await context.new_page()

            await page.goto("https://congress.gov.ph/legislative-documents/")
            
            # Wait for initial load
            await page.wait_for_selector('[id="20th Congress"]', state='visible', timeout=90000)
            
            # Set pagination to 100
            await page.locator("select.form-select").nth(1).select_option('100')    
            
            # Open dropdown
            await page.locator('[id="20th Congress"]').click()
            
            # Initial scroll and wait for first page items
            await page.wait_for_selector('.cursor-pointer.rounded-sm.border', state='visible')
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            # Skip pages if needed based on files array
            idx = 1
            for i in range(0, int(len(files) / 100)):
                print(f"Skipping page {i}\n")
                old_bill_id = await page.locator(".cursor-pointer span.rounded.border span span").first.inner_text()
                next_button = page.locator('li.next:not(.disabled) a') # Specifically target the 'Next' link
                await next_button.click()
                try:
                    await page.wait_for_function(
                        f"""() => {{
                            const el = document.querySelector(".cursor-pointer span.rounded.border span span");
                            return el && el.innerText.trim() !== "{old_bill_id.strip()}";
                        }}""",
                        timeout=15000 # 15 seconds is usually enough for a data swap
                    )
                except:
                    # Fallback if JS check fails: wait for network to settle
                    await page.wait_for_load_state("networkidle")
                
                # Small buffer for the UI to stabilize
                await page.wait_for_timeout(3000)
                idx += 1

            while(idx <= 79):
                # Scrape current page
                hb_items_locator = page.locator('.cursor-pointer.rounded-sm.border')
                await get_files_from_page(hb_items_locator)
                
                print(f"Finished scraping page {idx}")

                # Get "Next" button locator
                next_button = page.locator('li.next:not(.disabled) a') 
                
                if await next_button.count() > 0:
                    # Capture ID of the first item to track when the data actually changes
                    old_bill_id = await page.locator(".cursor-pointer span.rounded.border span span").first.inner_text()
                    
                    # Click next button
                    await next_button.click()

                    # 4. Wait for Content Refresh from Page Change
                    try:
                        await page.wait_for_function(
                            f"""() => {{
                                const el = document.querySelector(".cursor-pointer span.rounded.border span span");
                                return el && el.innerText.trim() !== "{old_bill_id.strip()}";
                            }}""",
                            timeout=15000 # timeout buffer
                        )
                    except:
                        # Fallback if JS check fails: wait for network to settle
                        await page.wait_for_load_state("networkidle")
                    
                    # Small buffer for the UI to stabilize
                    await page.wait_for_timeout(3000)
                    idx += 1
                else:
                    print("No more pages available.")
                    break
    except:
        print("Error occurred. Saving progress...")

    # Processing logic (e.g., saving to JSON)
    with open('outputs/metadata.json', mode='w', encoding='utf-8') as f:
        json.dump(
            obj=list(files),
            fp=f,
            default=json_encoder,
            indent=4
        )
        
if __name__ == '__main__':
    asyncio.run(main())