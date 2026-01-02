import fitz
import os
import sys

def convert_epub_to_pdf(epub_path, pdf_path):
    try:
        if not os.path.exists(epub_path):
            print(f"Error: File not found at {epub_path}")
            return

        print(f"Opening {epub_path}...")
        doc = fitz.open(epub_path)
        
        print("Converting to PDF...")
        pdf_bytes = doc.convert_to_pdf()
        
        pdf_doc = fitz.open("pdf", pdf_bytes)
        print(f"Saving to {pdf_path}...")
        pdf_doc.save(pdf_path)
        
        print("Done!")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        epub_file = sys.argv[1]
        if len(sys.argv) > 2:
            pdf_file = sys.argv[2]
        else:
            pdf_file = epub_file.rsplit(".", 1)[0] + ".pdf"
        convert_epub_to_pdf(epub_file, pdf_file)
    else:
        # Default behavior for the specific file requested
        epub_file = r"C:\Users\Cybr\Downloads\Technical Analysis for Beginners_ Candlestick Trading, -- Elder, Andrew -- United States, 2021 -- Andrew Elder -- 9781803032610 -- a49b4392e85e68dcfd52dce130b9754f -- Anna’s Archive.epub"
        pdf_file = epub_file.rsplit(".", 1)[0] + ".pdf"
        convert_epub_to_pdf(epub_file, pdf_file)
