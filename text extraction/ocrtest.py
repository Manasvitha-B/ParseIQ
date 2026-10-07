import sys
import json
import os
import pytesseract
from PIL import Image

def run_ocr_on_image(image_path):
    """
    Performs rigorous OCR checks on any input image file, extracting text blocks,
    precise bounding boxes, and confidence metrics in the standard common format.
    """
    if not os.path.exists(image_path):
        print(json.dumps({"error": f"Image file not found: {image_path}"}, indent=2))
        return

    try:
        img = Image.open(image_path)
        width, height = img.size
    except Exception as e:
        print(json.dumps({"error": f"Failed to open image: {str(e)}"}, indent=2))
        return

    # Extract OCR dictionary data
    ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    
    extracted_elements = []
    n_boxes = len(ocr_data['text'])
    
    for i in range(n_boxes):
        text = ocr_data['text'][i].strip()
        conf = float(ocr_data['conf'][i])
        
        # Filter out noise and blank text blocks
        if text and conf > 0:
            x0 = ocr_data['left'][i]
            y0 = ocr_data['top'][i]
            x1 = x0 + ocr_data['width'][i]
            y1 = y0 + ocr_data['height'][i]
            
            # Simple structure classification
            elem_type = "heading" if len(text) < 40 and not text.endswith('.') else "paragraph"
            if text.startswith(('-', '*', '•')):
                elem_type = "list_item"

            extracted_elements.append({
                "type": elem_type,
                "text": text,
                "confidence": round(conf / 100.0, 2),
                "bbox": [x0, y0, x1, y1],
                "source": "ocr_standalone"
            })

    output = {
        "source_image": image_path,
        "dimensions": {"width": width, "height": height},
        "total_elements_extracted": len(extracted_elements),
        "elements": extracted_elements
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_ocr_on_image(sys.argv[1])
    else:
        print("Usage: python ocr_test.py <path_to_image.png>")