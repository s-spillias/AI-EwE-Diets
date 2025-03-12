import fitz  # PyMuPDF
import csv
import os

def extract_comments(pdf_path, output_csv):
    doc = fitz.open(pdf_path)
    comments = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        for annot in page.annots():  # Iterate through annotations
            comment_text = annot.info.get("content", "").strip()
            author = annot.info.get("title", "Unknown")
            annot_type = annot.type[1]  # Get annotation type (e.g., Highlight, Note)
            rect = annot.rect  # Get coordinates
            
            # Get highlighted text if it's a highlight annotation
            highlighted_text = ""
            if annot_type == "Highlight":
                # Get the words that intersect with the highlight annotation
                words = page.get_text("words")
                rect = annot.rect
                for word in words:
                    word_rect = fitz.Rect(word[0:4])  # word rectangle
                    if rect.intersects(word_rect):
                        highlighted_text += word[4] + " "  # word[4] is the text
                highlighted_text = highlighted_text.strip()
            
            # Get surrounding context for sticky notes (about 200 characters around the annotation)
            context_text = ""
            if annot_type == "Text":  # Sticky notes
                # Get words near the annotation
                words = page.get_text("words")
                annotation_point = (rect.x0, rect.y0)
                
                # Sort words by distance to annotation
                words_with_distance = []
                for word in words:
                    word_point = (word[0], word[1])  # x, y coordinates of word
                    distance = ((word_point[0] - annotation_point[0])**2 + 
                              (word_point[1] - annotation_point[1])**2)**0.5
                    words_with_distance.append((distance, word[4]))  # word[4] is the text
                
                # Get closest words
                words_with_distance.sort()
                closest_words = words_with_distance[:20]  # Get 20 closest words
                context_text = " ".join(word[1] for word in closest_words)
            
            if comment_text or highlighted_text:  # Save if there's either a comment or highlighted text
                comments.append([
                    page_num + 1,
                    annot_type,
                    comment_text,
                    highlighted_text,
                    context_text,
                    author
                ])

    # Save to CSV
    with open(output_csv, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Page", "Type", "Comment", "Highlighted Text", "Context", "Author"])  # Header
        writer.writerows(comments)

    print(f"Extracted {len(comments)} comments from {os.path.basename(pdf_path)}. Saved to {os.path.basename(output_csv)}")

def process_directory(directory):
    # Process all PDF files in the directory
    for filename in os.listdir(directory):
        if filename.endswith('.pdf'):
            pdf_path = os.path.join(directory, filename)
            # Create output CSV name by replacing .pdf with _comments.csv
            output_csv = os.path.join(directory, filename.replace('.pdf', '_comments.csv'))
            extract_comments(pdf_path, output_csv)

if __name__ == "__main__":
    # Get the directory containing this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    process_directory(current_dir)
