#!/usr/bin/env python3
"""
Script to extract annotations from a PDF file, particularly highlighted text and comments.
"""

import fitz  # PyMuPDF
import os
import json
from datetime import datetime

def extract_annotations(pdf_path):
    """
    Extract annotations from a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        list: List of dictionaries containing annotation information
    """
    annotations = []
    
    # Open the PDF file
    doc = fitz.open(pdf_path)
    
    # Iterate through each page
    for page_num, page in enumerate(doc):
        # Get annotations
        page_annots = page.annots()
        
        if page_annots:
            for annot in page_annots:
                annot_info = {
                    "page": page_num + 1,
                    "type": annot.type[1],
                    "rect": list(annot.rect),
                    "colors": {
                        "stroke": annot.colors.get("stroke"),
                        "fill": annot.colors.get("fill")
                    },
                    "creation_date": annot.info.get("creationDate", ""),
                    "modification_date": annot.info.get("modDate", ""),
                    "author": annot.info.get("title", ""),
                    "content": annot.info.get("content", "")
                }
                
                # For highlights, extract the highlighted text
                if annot.type[1] == "Highlight":
                    words = page.get_text("words")
                    highlighted_text = ""
                    
                    # Find words that intersect with the highlight annotation
                    for word in words:
                        word_rect = fitz.Rect(word[:4])
                        if annot.rect.intersects(word_rect):
                            highlighted_text += word[4] + " "
                    
                    annot_info["highlighted_text"] = highlighted_text.strip()
                
                annotations.append(annot_info)
    
    doc.close()
    return annotations

def format_output(annotations):
    """
    Format the annotations for output.
    
    Args:
        annotations (list): List of annotation dictionaries
        
    Returns:
        str: Formatted output string
    """
    output = []
    
    for i, annot in enumerate(annotations, 1):
        entry = f"Annotation {i}:\n"
        entry += f"  Page: {annot['page']}\n"
        entry += f"  Type: {annot['type']}\n"
        
        if annot['type'] == "Highlight" and "highlighted_text" in annot:
            entry += f"  Highlighted Text: \"{annot['highlighted_text']}\"\n"
        
        if annot['content']:
            entry += f"  Comment: \"{annot['content']}\"\n"
        
        if annot['author']:
            entry += f"  Author: {annot['author']}\n"
        
        output.append(entry)
    
    return "\n".join(output)

def main():
    # Path to the PDF file
    pdf_path = "CoAuthorComments/Automated_Diet_Matrix_Construction_for_Marine_BL_comments.pdf"
    
    # Check if the file exists
    if not os.path.exists(pdf_path):
        print(f"Error: File '{pdf_path}' not found.")
        return
    
    # Extract annotations
    annotations = extract_annotations(pdf_path)
    
    if not annotations:
        print("No annotations found in the PDF.")
        return
    
    # Format and print the output
    formatted_output = format_output(annotations)
    print(formatted_output)
    
    # Save the output to a text file
    output_file = "CoAuthorComments/pdf_annotations.txt"
    with open(output_file, "w") as f:
        f.write(formatted_output)
    
    print(f"\nAnnotations saved to '{output_file}'")
    
    # Save the raw annotation data as JSON for further processing if needed
    json_file = "pdf_annotations.json"
    with open(json_file, "w") as f:
        json.dump(annotations, f, indent=2, default=str)
    
    print(f"Raw annotation data saved to '{json_file}'")

if __name__ == "__main__":
    main()
