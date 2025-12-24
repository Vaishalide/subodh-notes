import os
import shutil
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
# Import Image reader and color helpers
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import blue, black, darkgray
from pypdf import PdfReader, PdfWriter

# Define the logo filename expected in the root directory
LOGO_FILENAME = "logo.jpg"

def add_watermark_page(input_path, output_path, website_name="NoteHub", website_link="https://your-website.com"):
    watermark_file = "watermark_temp.pdf"
    try:
        # 1. Create the Watermark/Cover Page canvas
        c = canvas.Canvas(watermark_file, pagesize=letter)
        width, height = letter # Standard Letter size (612.0 x 792.0 points)
        centerX = width / 2
        centerY = height / 2

        # --- Layout Configuration (Vertical positions from top to bottom) ---
        # Adjust these values to move elements up or down
        y_title = centerY + 160      # "Downloaded From"
        y_image_center = centerY + 60 # Center point for the image
        y_site_name = centerY - 40   # Website Name (e.g., NoteHub)
        y_subtext = centerY - 90     # "Visit for more..."
        y_link = centerY - 120       # The clickable website link
        y_insta = centerY - 180      # New Instagram footer note

        # --- Drawing Elements ---

        # 1. Draw Title text
        c.setFont("Helvetica-Bold", 24)
        c.setFillColor(black)
        c.drawCentredString(centerX, y_title, "Downloaded From")

        # 2. Draw Image/Logo (Safely)
        if os.path.exists(LOGO_FILENAME):
            try:
                img = ImageReader(LOGO_FILENAME)
                img_width, img_height = img.getSize()
                
                # Define maximum display size (e.g., 200 points wide) so big logos don't break layout
                max_width = 200
                aspect_ratio = img_height / float(img_width)
                
                display_width = min(max_width, img_width)
                display_height = display_width * aspect_ratio

                # Calculate bottom-left coordinates to center the image
                img_x = centerX - (display_width / 2)
                img_y = y_image_center - (display_height / 2)

                # Draw the image
                # mask='auto' helps with transparent PNGs
                c.drawImage(img, img_x, img_y, width=display_width, height=display_height, mask='auto')
            except Exception as img_err:
                print(f"Warning: Could not process image: {img_err}")
                # Optional: Draw placeholder text if image fails to load properly
                # c.setFont("Helvetica-Oblique", 10)
                # c.setFillColor(darkgray)
                # c.drawCentredString(centerX, y_image_center, "(Logo Error)")
        # Else: if logo.png doesn't exist, just leave space empty

        # 3. Draw Website Name (Big, Blue)
        c.setFont("Helvetica-Bold", 36)
        c.setFillColor(blue)
        c.drawCentredString(centerX, y_site_name, website_name)

        # 4. Draw Subtext
        c.setFont("Helvetica", 14)
        c.setFillColor(black)
        c.drawCentredString(centerX, y_subtext, "Visit for more Notes & PYQs:")

        # 5. Add Clickable Link (Blue)
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(blue)
        c.drawCentredString(centerX, y_link, website_link)
        
        # Calculate clickable area rectangle dynamically based on text width
        link_width = c.stringWidth(website_link, "Helvetica-Bold", 14)
        link_rect = (
            centerX - (link_width / 2) - 5, # x1
            y_link - 5,                     # y1
            centerX + (link_width / 2) + 5, # x2
            y_link + 15                     # y2 (approx font height)
        )
        c.linkURL(website_link, link_rect, relative=1)

        # 6. Add New Instagram Note (Footer style, dark gray)
        insta_text = "Site is made by instagram @dipesh_yadav_05"
        c.setFont("Helvetica", 11)
        c.setFillColor(darkgray)
        c.drawCentredString(centerX, y_insta, insta_text)

        # Finalize cover page
        c.showPage()
        c.save()

        # --- Merge Processes (Existing Logic) ---
        writer = PdfWriter()
        
        # Add the newly created cover page first
        cover_reader = PdfReader(watermark_file)
        writer.add_page(cover_reader.pages[0])
        
        # Add all pages from original PDF
        original_reader = PdfReader(input_path)
        for page in original_reader.pages:
            writer.add_page(page)
        
        # Save the final merged PDF
        with open(output_path, "wb") as f:
            writer.write(f)
            
    except Exception as e:
        print(f"PDF Processing Error: {e}")
        # Fallback: If processing fails, copy original file so upload continues
        shutil.copy(input_path, output_path)
    finally:
        # Cleanup temporary cover file
        if os.path.exists(watermark_file):
            os.remove(watermark_file)
