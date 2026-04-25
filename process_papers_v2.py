
import os
import re
import shutil
import pdfplumber
from collections import defaultdict, Counter

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                if i > 5:  # Only read first 6 pages to save time
                    break
                text += page.extract_text() or ""
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return text

def clean_filename(title, index):
    # Remove special characters and replace spaces with underscores
    cleaned = re.sub(r'[^\w\s-]', '', title)
    cleaned = re.sub(r'\s+', '_', cleaned.strip())
    # Limit length and add index for uniqueness
    return f"{cleaned[:100]}_{index}.pdf"

def determine_category(text, filename, bib_entry):
    # Keywords to check
    supervised_keywords = ["supervised learning", "labeled data", "fully labeled"]
    semi_supervised_keywords = ["semi-supervised", "semi supervised", "semisupervised", "partially labeled", "limited labeled data"]
    self_supervised_keywords = ["self-supervised", "self supervised", "selfsupervised", "contrastive learning", "pre-training", "foundation model", "channel charting", "pre-trained"]
    
    category = None
    reasons = []
    
    # Check filename first
    filename_lower = filename.lower()
    if "semi" in filename_lower:
        reasons.append("Filename contains 'semi'")
        category = "半监督"
    elif any(kw in filename_lower for kw in ["self", "foundation", "channel charting", "pre-train"]):
        reasons.append("Filename suggests self-supervised/foundation model/channel charting")
        category = "自监督"
    
    # Check text
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in semi_supervised_keywords):
        reasons.append("Text contains semi-supervised keywords")
        category = "半监督"
    elif any(keyword in text_lower for keyword in self_supervised_keywords):
        reasons.append("Text contains self-supervised keywords")
        category = "自监督"
    elif any(keyword in text_lower for keyword in supervised_keywords):
        reasons.append("Text contains supervised keywords")
        category = "监督"
    
    # Fallback: if no category found, use bib entry keywords if available
    if not category and bib_entry:
        bib_lower = bib_entry.lower()
        if any(keyword in bib_lower for keyword in semi_supervised_keywords):
            reasons.append("Bib entry contains semi-supervised keywords")
            category = "半监督"
        elif any(keyword in bib_lower for keyword in self_supervised_keywords):
            reasons.append("Bib entry contains self-supervised keywords")
            category = "自监督"
        elif any(keyword in bib_lower for keyword in supervised_keywords):
            reasons.append("Bib entry contains supervised keywords")
            category = "监督"
    
    # Default to supervised if nothing else
    if not category:
        reasons.append("No specific keywords found, defaulting to supervised")
        category = "监督"
    
    return category, "; ".join(reasons)

def load_bib_entries():
    bib_entries = {}
    # Load bib files from each folder
    for folder in ["半监督", "监督", "自监督"]:
        bib_path = os.path.join(folder, f"{folder}bib.txt")
        if os.path.exists(bib_path):
            with open(bib_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Split into entries (simplified)
                entries = re.split(r'(?=@)', content)
                for entry in entries:
                    if entry.strip():
                        # Extract title
                        title_match = re.search(r'title\s*=\s*{([^}]+)}', entry, re.IGNORECASE)
                        if title_match:
                            title = title_match.group(1).strip()
                            bib_entries[title.lower()] = entry
    return bib_entries

def main():
    base_dir = "/workspace"
    folders = ["半监督", "监督", "自监督"]
    bib_entries = load_bib_entries()
    
    # First, let's clean up the previous copies (remove all PDFs in the folders except original)
    # Wait, let's instead create a backup of original PDFs first
    backup_dir = os.path.join(base_dir, "original_backup")
    os.makedirs(backup_dir, exist_ok=True)
    for folder in folders:
        folder_backup = os.path.join(backup_dir, folder)
        os.makedirs(folder_backup, exist_ok=True)
        folder_path = os.path.join(base_dir, folder)
        for filename in os.listdir(folder_path):
            if filename.endswith(".pdf"):
                shutil.copy2(os.path.join(folder_path, filename), os.path.join(folder_backup, filename))
    print("Backup of original PDFs created.")
    
    # Now, remove all PDFs from the original folders to start fresh
    for folder in folders:
        folder_path = os.path.join(base_dir, folder)
        for filename in os.listdir(folder_path):
            if filename.endswith(".pdf"):
                os.remove(os.path.join(folder_path, filename))
    
    # Track all papers
    all_papers = []
    # Track papers per category for bib update
    category_bibs = defaultdict(list)
    # Track used titles to avoid duplicates
    title_counter = Counter()
    
    # Process all PDFs from backup
    for folder in folders:
        folder_backup = os.path.join(backup_dir, folder)
        for filename in os.listdir(folder_backup):
            if filename.endswith(".pdf"):
                pdf_path = os.path.join(folder_backup, filename)
                print(f"Processing {pdf_path}...")
                
                # Extract text
                text = extract_text_from_pdf(pdf_path)
                
                # Try to find title
                title = None
                # First, check bib entries by filename similarity
                for bib_title in bib_entries:
                    # Split into words and check overlap
                    bib_words = set(re.split(r'\W+', bib_title.lower()))
                    filename_words = set(re.split(r'\W+', filename.lower().replace('.pdf', '')))
                    overlap = bib_words & filename_words
                    if len(overlap) >= 2:
                        title = bib_title
                        break
                # If not found, try to extract from first page of text
                if not title and text:
                    lines = text.split('\n')[:30]
                    for line in lines:
                        line = line.strip()
                        if (len(line) > 15 and 
                            not line.lower().startswith(('abstract', 'introduction', 'keywords', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')) and
                            not any(kw in line.lower() for kw in ['arxiv', 'ieee', 'acm', 'workshop', 'conference', 'journal'])):
                            title = line
                            break
                # If still not found, use filename (without .pdf)
                if not title:
                    title = filename.replace('.pdf', '').replace('_', ' ')
                
                # Determine category
                category, reasons = determine_category(text, filename, bib_entries.get(title.lower()))
                
                # Get unique index for filename
                title_key = title.lower()
                title_counter[title_key] += 1
                index = title_counter[title_key]
                
                # Clean new filename
                new_filename = clean_filename(title, index)
                
                # Track
                all_papers.append({
                    "original_folder": folder,
                    "original_filename": filename,
                    "title": title,
                    "new_filename": new_filename,
                    "category": category,
                    "reasons": reasons,
                    "text_snippet": text[:800]  # Keep a snippet for reference
                })
                
                # Add to category bibs if we have a bib entry
                if title.lower() in bib_entries:
                    category_bibs[category].append(bib_entries[title.lower()])
                
                # Copy to new location
                dest_folder = os.path.join(base_dir, category)
                dest = os.path.join(dest_folder, new_filename)
                os.makedirs(dest_folder, exist_ok=True)
                shutil.copy2(pdf_path, dest)
                print(f"Copied to {category}/{new_filename}")
    
    # Create classification record
    record_path = os.path.join(base_dir, "classification_record.md")
    with open(record_path, 'w', encoding='utf-8') as f:
        f.write("# 论文分类记录\n\n")
        for paper in all_papers:
            f.write(f"## {paper['title']}\n\n")
            f.write(f"- **原文件夹**: {paper['original_folder']}\n")
            f.write(f"- **新文件夹**: {paper['category']}\n")
            f.write(f"- **原文件名**: {paper['original_filename']}\n")
            f.write(f"- **新文件名**: {paper['new_filename']}\n")
            f.write(f"- **分类依据**: {paper['reasons']}\n\n")
            f.write(f"### 原文片段:\n```\n{paper['text_snippet']}\n```\n\n")
            f.write("---\n\n")
    
    # Update bib files
    for category in folders:
        bib_path = os.path.join(base_dir, category, f"{category}bib.txt")
        with open(bib_path, 'w', encoding='utf-8') as f:
            for entry in category_bibs.get(category, []):
                f.write(entry)
                f.write("\n\n")
        print(f"Updated {bib_path}")
    
    print("Processing complete!")

if __name__ == "__main__":
    main()
