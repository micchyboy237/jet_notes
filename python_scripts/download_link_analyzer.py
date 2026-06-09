import requests


def analyze_download_link(url):
    """
    Follows redirects of a link and determines if the final destination is a downloadable resource.
    """
    try:
        # Send a HEAD request. 'allow_redirects=True' is crucial for following short links.
        # It automatically follows the chain of redirects (e.g., 301, 302) to the final URL.
        response = requests.head(url, allow_redirects=True, timeout=10)

        # The `response.url` will contain the final URL after all redirects.
        final_url = response.url
        print(f"Original URL: {url}")
        print(f"Final URL after redirects: {final_url}")

        # Check if the request was successful.
        if response.status_code == 200:
            print(f"\n[SUCCESS] Resource found (Status Code: {response.status_code})")

            # Get the 'Content-Type' from the headers to see what kind of file it is.
            content_type = response.headers.get("Content-Type", "unknown")
            print(f"Content Type: {content_type}")

            # Get the 'Content-Length' (file size) if the server provides it.
            content_length = response.headers.get("Content-Length")
            if content_length:
                # Convert size from bytes to a human-readable format (MB or KB)
                size_mb = int(content_length) / (1024 * 1024)
                print(f"File Size: ~{size_mb:.2f} MB")
            else:
                print("File Size: Not provided by server.")

            # Check if the final URL has a common file extension for downloads.
            download_extensions = [
                ".pdf",
                ".zip",
                ".exe",
                ".dmg",
                ".apk",
                ".rar",
                ".7z",
                ".tar.gz",
                ".iso",
            ]
            is_download = any(
                final_url.lower().endswith(ext) for ext in download_extensions
            )

            # A downloadable file often has an 'application/octet-stream' or other binary content type.
            is_binary = (
                "application/" in content_type
                or "video/" in content_type
                or "audio/" in content_type
            )

            if is_download or is_binary:
                print("\n[VERDICT] This link likely points to a downloadable file.")
            else:
                print(
                    "\n[VERDICT] This link likely points to a webpage, not a direct download."
                )

        else:
            print(
                f"\n[FAILURE] Link is broken or inaccessible (Status Code: {response.status_code})"
            )

    except requests.exceptions.Timeout:
        print(
            "[ERROR] The request timed out. The server might be slow or unresponsive."
        )
    except requests.exceptions.TooManyRedirects:
        print("[ERROR] The link resulted in too many redirects.")
    except requests.exceptions.RequestException as e:
        # This catches other errors like invalid URL, connection problems, etc.
        print(f"[ERROR] An error occurred: {e}")


# --- Example Usage with your provided link ---
if __name__ == "__main__":
    test_url = "https://filester.si/d/brfAIB7"
    analyze_download_link(test_url)
