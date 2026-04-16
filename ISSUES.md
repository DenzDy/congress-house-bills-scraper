# Scraper Issues Report

> Generated: 2026-04-17  
> File analyzed: `scraper.ipynb`

---

## Summary

Two categories of issues were found:

1. **Item-skipping risks** — ways the scraper can silently miss bills on any given page
2. **Data integrity bugs** — ways scraped data can be wrong or cause unnecessary re-downloads

---

## Category 1: Item-Skipping Risks

### 🔴 ISSUE-01 — `count()` Is Called Before Items Render (Lazy Load Risk)

**Location:** `get_files_from_page()` function

**Code:**
```python
count = await hb_items_locator.count()   # snapshot taken immediately
for i in range(count):
    hb_item = hb_items_locator.nth(i)
    await hb_item.scroll_into_view_if_needed()  # scroll happens AFTER count is fixed
```

**Problem:**  
`count()` captures how many items are currently in the DOM **at the moment it is called** — before any scrolling. If the website uses lazy rendering (items are only inserted into the DOM when scrolled into view), then `count()` returns only the number of items already visible in the 500px-tall viewport window, not all 100 items on the page. Every item below the fold that hasn't yet rendered would be silently skipped.

The initial page has a partial workaround (`window.scrollTo(0, document.body.scrollHeight)`) but this only runs **once before page 1**. For all subsequent pages (2–101), no pre-scroll is done before `get_files_from_page` is called, making this a consistent risk on every page after the first.

**Fix:**  
Scroll to the bottom of the page before calling `get_files_from_page` on every page iteration, to force all items to render before `count()` is called:

```python
while idx <= last_page:
    # Force all lazy-loaded items to render before counting
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1000)

    hb_items_locator = page.locator('.cursor-pointer.rounded-sm.border')
    await get_files_from_page(hb_items_locator)
    ...
```

---

### 🔴 ISSUE-02 — Page Transition Wait Only Checks the First Item

**Location:** Main scraper loop, after `next_button.click()`

**Code:**
```python
await page.wait_for_function(
    """() => {
        const el = document.querySelector(".cursor-pointer span.rounded.border span span");
        return el && el.innerText.trim() !== "<old_bill_id>";
    }""",
    timeout=15000
)
await page.wait_for_timeout(3000)
```

**Problem:**  
`document.querySelector(...)` selects only the **first** matching element. This check passes as soon as the first bill's ID changes — which can happen when only the first few items have loaded. The remaining items may still be rendering when the 3-second buffer starts, and `count()` is called while the DOM is incomplete.

On a slow server or slow network, 3 seconds may not be enough for all 100 items to render.

**Fix:**  
After the wait, also wait for the expected count of items:

```python
await page.wait_for_function(
    """() => {
        const items = document.querySelectorAll(".cursor-pointer.rounded-sm.border");
        return items.length >= 100;  // or the expected count per page
    }""",
    timeout=15000
)
```

Or combine with the pre-scroll fix in ISSUE-01 since scrolling also naturally forces the DOM to stabilize.

---

### 🟡 ISSUE-03 — Unhandled Exception Aborts All Remaining Pages

**Location:** Main scraper loop (outer `try/except`)

**Code:**
```python
try:
    async with AsyncCamoufox(...) as browser:
        while idx <= last_page:
            await get_files_from_page(hb_items_locator)
            ...
except Exception as e:
    print("Error occurred. Saving progress...")
    print(f"{e}")
```

**Problem:**  
Any unhandled exception anywhere inside the loop (e.g., a network timeout while extracting text, a Playwright element not found error) causes the entire remaining scrape to abort. All pages after the failure point are skipped, with only a single printed message as indication.

**Fix:**  
Wrap the per-page scrape in its own try/except with retry logic:

```python
import asyncio

MAX_RETRIES = 3

while idx <= last_page:
    for attempt in range(MAX_RETRIES):
        try:
            hb_items_locator = page.locator('.cursor-pointer.rounded-sm.border')
            await get_files_from_page(hb_items_locator)
            break  # success, exit retry loop
        except Exception as e:
            print(f"Error on page {idx}, attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(3)
            else:
                print(f"Skipping page {idx} after {MAX_RETRIES} failed attempts.")
    ...
```

---

### 🟡 ISSUE-04 — `last_page` Is a One-Time Snapshot

**Location:** Main scraper loop setup

**Code:**
```python
last_page = int(await page.locator('ul.pagination > li').nth(-2).inner_text())
```

**Problem:**  
`last_page` is read once before the loop. If new bills are added to the website during an ongoing scrape (increasing the total page count), the new pages will never be visited. This is low-risk for a short run but relevant for long-running jobs.

**Fix:**  
Re-read `last_page` at the start of each iteration, or rely solely on the "Next" button being disabled/absent as the termination condition (which the code already has as a fallback):

```python
while True:
    hb_items_locator = page.locator('.cursor-pointer.rounded-sm.border')
    await get_files_from_page(hb_items_locator)
    print(f"Finished scraping page {idx}")

    next_button = page.locator('li.next:not(.disabled) a')
    if await next_button.count() > 0:
        ...
        idx += 1
    else:
        print("No more pages available.")
        break
```

---

## Category 2: Data Integrity Bugs

### 🔴 ISSUE-05 — JSON Key Mismatch: `"Downloaded"` vs `"Downloadable"`

**Location:** `load_files_from_json()` vs `json_encoder()`

**Code:**
```python
# json_encoder saves as:
'Downloadable': obj.is_file_downloadable

# load_files_from_json reads as:
is_file_downloadable=item.get("Downloaded", False)  # ← wrong key
```

**Problem:**  
The key `"Downloaded"` does not exist in the JSON — the correct key is `"Downloadable"`. Every time the metadata file is loaded, `is_file_downloadable` defaults to `False` for every bill. This causes the scraper to attempt to re-download every PDF with a valid link on every single run, downloading thousands of already-downloaded files unnecessarily.

**Fix:**
```python
is_file_downloadable=item.get("Downloadable", False)
```

---

### 🟡 ISSUE-06 — `new_downloads` Counter Increments on Failed Downloads

**Location:** `get_files_from_page()`, download block

**Code:**
```python
downloadability = download(link, "outputs/")
new_downloads += 1  # ← always incremented, even if download() returns False
```

**Problem:**  
`download()` returns `False` on failure, but the counter is incremented regardless. The final report will overcount successful downloads.

**Fix:**
```python
downloadability = download(link, "outputs/")
if downloadability:
    new_downloads += 1
```

---

### 🟡 ISSUE-07 — `is_file_downloadable` Not Updated When PDF Link Changes

**Location:** `get_files_from_page()`, metadata update block

**Code:**
```python
if new_file.text_filed != matched_hb.text_filed and new_file.text_filed != 'N/A':
    matched_hb.text_filed = new_file.text_filed
    matched_hb.date_scraped = today
    matched_hb.date_filed = new_file.date_filed
    # ← matched_hb.is_file_downloadable is never updated
```

**Problem:**  
When an existing bill gets a new PDF link and is re-downloaded, the `is_file_downloadable` flag on the stored record is never updated to reflect the new download status.

**Fix:**
```python
if new_file.text_filed != matched_hb.text_filed and new_file.text_filed != 'N/A':
    matched_hb.text_filed = new_file.text_filed
    matched_hb.date_scraped = today
    matched_hb.date_filed = new_file.date_filed
    matched_hb.is_file_downloadable = downloadability  # ← add this line
```

---

### 🟡 ISSUE-08 — Bare `except` Silently Converts All Metadata Errors to `"N/A"`

**Location:** `get_meta()` inside `get_files_from_page()`

**Code:**
```python
async def get_meta(label):
    try:
        ...
        text = await value_locator.first.inner_text(timeout=1000)
        return text.strip()
    except:          # catches ALL exceptions including TimeoutError
        return "N/A"
```

**Problem:**  
If an element isn't found or doesn't load within 1 second (e.g., due to AOS not triggering, slow render, or a DOM structure change), the field silently becomes `"N/A"`. The bill is still saved, but with corrupted/missing metadata. There is no way to distinguish legitimate `"N/A"` values from errors.

**Fix:**  
At minimum, log the failure:
```python
async def get_meta(label):
    try:
        ...
        return text.strip()
    except Exception as e:
        print(f"[WARN] Could not get '{label}' for item — {type(e).__name__}")
        return "N/A"
```

---

## Issue Priority Summary

| ID | Severity | Category | Issue |
|----|----------|----------|-------|
| ISSUE-01 | 🔴 High | Item-skipping | `count()` called before lazy items render |
| ISSUE-02 | 🔴 High | Item-skipping | Page transition only waits for first item |
| ISSUE-05 | 🔴 High | Data integrity | JSON key mismatch causes all re-downloads |
| ISSUE-03 | 🟡 Medium | Item-skipping | Any exception kills all remaining pages |
| ISSUE-06 | 🟡 Medium | Data integrity | Download counter inflated by failures |
| ISSUE-07 | 🟡 Medium | Data integrity | `is_file_downloadable` not updated on re-download |
| ISSUE-08 | 🟡 Medium | Data integrity | Silent `"N/A"` on metadata errors |
| ISSUE-04 | 🟢 Low | Item-skipping | `last_page` not refreshed mid-run |
