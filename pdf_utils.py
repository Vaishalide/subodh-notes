import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import blue, black
from pypdf import PdfReader, PdfWriter

def add_watermark_page(input_path, output_path, website_name="NoteHub", website_link="https://your-website.com"):
    # 1. Create the Watermark/Cover Page
    watermark_file = "watermark_temp.pdf"
    c = canvas.Canvas(watermark_file, pagesize=letter)
    width, height = letter
    
    # Draw Background/Text
    c.setFont("Helvetica-Bold", 30)
    c.setFillColor(black)
    c.drawCentredString(width / 2, height / 2 + 50, "Downloaded From")
    
    c.setFont("Helvetica-Bold", 40)
    c.setFillColor(blue)
    c.drawCentredString(width / 2, height / 2, website_name)
    
    c.setFont("Helvetica", 15)
    c.setFillColor(black)
    c.drawCentredString(width / 2, height / 2 - 50, "Visit for more Notes & PYQs:")
    
    # Add Clickable Link
    c.setFillColor(blue)
    c.drawString(width / 2 - 100, height / 2 - 80, website_link)
    c.linkURL(website_link, (width/2 - 100, height/2 - 90, width/2 + 100, height/2 - 70), relative=1)
    
    c.showPage()
    c.save()

    # 2. Merge Cover Page + Original PDF
    writer = PdfWriter()
    
    # Add Cover Page
    cover_reader = PdfReader(watermark_file)
    writer.add_page(cover_reader.pages[0])
    
    # Add Original Pages
    original_reader = PdfReader(input_path)
    for page in original_reader.pages:
        writer.add_page(page)
    
    # Save Final
    with open(output_path, "wb") as f:
        writer.write(f)
        
    # Cleanup temp cover
    if os.path.exists(watermark_file):
        os.remove(watermark_file)
