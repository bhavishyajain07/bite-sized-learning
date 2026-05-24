import ssl
import trafilatura
import urllib.request

ssl._create_default_https_context = ssl._create_unverified_context

url = "https://www.geeksforgeeks.org/machine-learning/"

# Pretend to be a real browser by sending a User-Agent header
req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    },
)

with urllib.request.urlopen(req) as response:
    html = response.read().decode("utf-8", errors="ignore")

# Now hand the HTML to trafilatura
text = trafilatura.extract(html)

if text is None:
    print("⚠️ Still failed. Try the fallback URL below.")
else:
    print(f"--- Extracted {len(text)} characters ---\n")
    print("--- First 800 characters ---")
    print(text[:800])
    print("\n\n--- Last 400 characters ---")
    print(text[-400:])
