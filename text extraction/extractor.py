import sys
import json
import os
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

def classify_element(text):
    """
    Heuristic rule to classify text into headings, lists, or paragraphs.
    """
    text_stripped = text.strip()
    if not text_stripped:
        return "paragraph"
    
    # Check for lists (bullet points, dashes, numbers like '1.', 'a)')
    if text_stripped.startswith(('-', '*', '•')) or (len(text_stripped) > 2 and text_stripped[0].isdigit() and text_stripped[1] in ['.', ')']):
        return "list_item"
    
    # Check for headings (short text, usually no ending punctuation like period)
    if len(text_stripped) < 80 and not text_stripped.endswith(('.', '?', '!')):
        return "heading"
        
    return "paragraph"

def extract_document(file_path, doc_id="doc_001"):
    """
    Extracts text from a PDF document or a standalone image file.
    Automatically switches between digital text extraction and OCR.
    """
    if not os.path.exists(file_path):
        return json.dumps({"error": f"File not found: {file_path}"}, indent=2)

    ext = os.path.splitext(file_path)[1].lower()
    
    document_output = {
        "document_id": doc_id,
        "source_file": os.path.basename(file_path),
        "pages": []
    }

    # --- CASE 1: Standalone Image File ---
    if ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        try:
            img = Image.open(file_path)
            width, height = img.size
            ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            elements = []
            n_boxes = len(ocr_data['text'])
            for i in range(n_boxes):
                text = ocr_data['text'][i].strip()
                conf = float(ocr_data['conf'][i])
                
                if text and conf > 0:
                    x0 = ocr_data['left'][i]
                    y0 = ocr_data['top'][i]
                    x1 = x0 + ocr_data['width'][i]
                    y1 = y0 + ocr_data['height'][i]
                    
                    elements.append({
                        "type": classify_element(text),
                        "text": text,
                        "confidence": round(conf / 100.0, 2),
                        "bbox": [x0, y0, x1, y1],
                        "source": "ocr_image"
                    })
            
            document_output["pages"].append({
                "page_number": 1,
                "page_dimensions": {"width": width, "height": height},
                "elements": elements
            })
        except Exception as e:
            return json.dumps({"error": f"Image processing error: {str(e)}"}, indent=2)

    # --- CASE 2: PDF Document (Digital & Scanned Pages) ---
    elif ext == '.pdf':
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            return json.dumps({"error": f"Error opening PDF: {str(e)}"}, indent=2)

        document_output["total_pages"] = len(doc)

        for page_num in range(len(doc)):
            page = doc[page_num]
            rect = page.rect
            page_data = {
                "page_number": page_num + 1,
                "page_dimensions": {"width": round(rect.width, 2), "height": round(rect.height, 2)},
                "elements": []
            }

            # Get native text blocks: (x0, y0, x1, y1, text, block_no, block_type)
            blocks = page.get_text("blocks")
            has_digital_text = any(b[4].strip() for b in blocks if b[6] == 0)

            if has_digital_text:
                # --- DIGITAL EXTRACTION ---
                for b in blocks:
                    if b[6] == 0:  # Text block type
                        text_content = b[4].strip()
                        if not text_content:
                            continue
                        
                        page_data["elements"].append({
                            "type": classify_element(text_content),
                            "text": text_content,
                            "confidence": 1.0,  # Native text has 100% confidence
                            "bbox": [round(b[0], 2), round(b[1], 2), round(b[2], 2), round(b[3], 2)],
                            "source": "digital_pdf"
                        })
            else:
                # --- OCR FALLBACK FOR SCANNED PDF PAGES ---
                zoom = 300 / 72  # 300 DPI high-res rendering
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))

                ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                scale_x = rect.width / img.width
                scale_y = rect.height / img.height

                n_boxes = len(ocr_data['text'])
                for i in range(n_boxes):
                    text = ocr_data['text'][i].strip()
                    conf = float(ocr_data['conf'][i])

                    if text and conf > 0:
                        x0 = ocr_data['left'][i] * scale_x
                        y0 = ocr_data['top'][i] * scale_y
                        x1 = (ocr_data['left'][i] + ocr_data['width'][i]) * scale_x
                        y1 = (ocr_data['top'][i] + ocr_data['height'][i]) * scale_y

                        page_data["elements"].append({
                            "type": classify_element(text),
                            "text": text,
                            "confidence": round(conf / 100.0, 2),
                            "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                            "source": "ocr_pdf"
                        })

            document_output["pages"].append(page_data)
    else:
        return json.dumps({"error": "Unsupported file format. Use PDF or image files."}, indent=2)

    return json.dumps(document_output, indent=2)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
        print(f"Processing file: {target_file}")
        print(extract_document(target_file))
    else:
        print("Usage: python extractor.py <path_to_pdf_or_image>")