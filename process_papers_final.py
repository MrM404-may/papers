
import os
import re
import shutil
import pdfplumber
from collections import defaultdict

def extract_text_from_pdf(pdf_path, max_pages=5):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                if i >= max_pages:
                    break
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return text

def clean_filename(title):
    # Remove special characters
    cleaned = re.sub(r'[^\w\s\-]', '', title)
    # Replace spaces with underscores
    cleaned = re.sub(r'\s+', '_', cleaned.strip())
    # Limit length
    return cleaned[:150] + ".pdf"

def determine_category(text, filename, bib_entry):
    supervised_keywords = ["supervised learning", "labeled data", "fully labeled", "supervised"]
    semi_supervised_keywords = ["semi-supervised", "semi supervised", "semisupervised", "partially labeled", "limited labeled data", "semi"]
    self_supervised_keywords = ["self-supervised", "self supervised", "selfsupervised", "contrastive", "pre-training", "foundation model", "channel charting", "pre-trained"]

    category = None
    reasons = []

    filename_lower = filename.lower()
    if any(kw in filename_lower for kw in semi_supervised_keywords):
        reasons.append("Filename contains semi-supervised keywords")
        category = "半监督"
    elif any(kw in filename_lower for kw in self_supervised_keywords):
        reasons.append("Filename suggests self-supervised/foundation model/channel charting")
        category = "自监督"

    text_lower = text.lower()
    if category is None and any(kw in text_lower for kw in semi_supervised_keywords):
        reasons.append("Text contains semi-supervised keywords")
        category = "半监督"
    elif category is None and any(kw in text_lower for kw in self_supervised_keywords):
        reasons.append("Text contains self-supervised keywords")
        category = "自监督"
    elif category is None and any(kw in text_lower for kw in supervised_keywords):
        reasons.append("Text contains supervised keywords")
        category = "监督"

    if category is None and bib_entry:
        bib_lower = bib_entry.lower()
        if any(kw in bib_lower for kw in semi_supervised_keywords):
            reasons.append("Bib entry contains semi-supervised keywords")
            category = "半监督"
        elif any(kw in bib_lower for kw in self_supervised_keywords):
            reasons.append("Bib entry contains self-supervised keywords")
            category = "自监督"
        elif any(kw in bib_lower for kw in supervised_keywords):
            reasons.append("Bib entry contains supervised keywords")
            category = "监督"

    if category is None:
        reasons.append("No specific keywords found, defaulting to supervised")
        category = "监督"

    return category, "; ".join(reasons)

def load_bib_entries(base_dir):
    bib_entries = {}
    for folder in ["半监督", "监督", "自监督"]:
        bib_path = os.path.join(base_dir, folder, f"{folder}bib.txt")
        if os.path.exists(bib_path):
            with open(bib_path, 'r', encoding='utf-8') as f:
                content = f.read()
                entries = re.split(r'(?=@[A-Za-z]+)', content)
                for entry in entries:
                    entry = entry.strip()
                    if entry:
                        title_match = re.search(r'title\s*=\s*\{([^}]+)\}', entry, re.IGNORECASE)
                        if title_match:
                            title = title_match.group(1).strip()
                            bib_entries[title.lower()] = entry
    return bib_entries

def main():
    base_dir = "/workspace"
    backup_dir = os.path.join(base_dir, "original_backup")
    
    # Make sure the target folders exist and are empty
    for folder in ["半监督", "监督", "自监督"]:
        folder_path = os.path.join(base_dir, folder)
        if os.path.exists(folder_path):
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if item.endswith(".pdf"):
                    os.remove(item_path)
        os.makedirs(folder_path, exist_ok=True)

    bib_entries = load_bib_entries(base_dir)
    all_papers = []
    category_bibs = defaultdict(list)

    for original_folder in ["半监督", "监督", "自监督"]:
        folder_backup = os.path.join(backup_dir, original_folder)
        if not os.path.exists(folder_backup):
            continue
        for filename in os.listdir(folder_backup):
            if not filename.endswith(".pdf"):
                continue
            pdf_path = os.path.join(folder_backup, filename)
            print(f"Processing {filename}...")

            text = extract_text_from_pdf(pdf_path)
            
            # Find title
            title = None
            # Try bib entries first by matching words in filename
            filename_words = set(re.split(r'[\W_]+', filename.lower().replace('.pdf', '')))
            for bib_title, bib_entry in bib_entries.items():
                bib_title_words = set(re.split(r'[\W_]+', bib_title))
                overlap = filename_words & bib_title_words
                if len(overlap) >= 3:
                    title = bib_title
                    break
            # If no bib match, extract from text
            if not title and text:
                lines = text.split('\n')
                for i, line in enumerate(lines[:30]):
                    stripped = line.strip()
                    if (len(stripped) > 10 and
                        not stripped.lower().startswith(('abstract', 'introduction', 'keywords', '1.', '2.', '3.', 'arxiv', 'ieee', 'acm')) and
                        not any(kw in stripped.lower() for kw in ['workshop', 'conference', 'journal', 'university'])):
                        # Check if next line is also part of title
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if len(next_line) > 5 and not next_line.lower().startswith(('abstract', 'introduction')):
                                stripped += " " + next_line
                        title = stripped
                        break
            if not title:
                title = filename.replace('.pdf', '').replace('_', ' ')
            
            # Find bib entry for this title
            bib_entry = bib_entries.get(title.lower())
            
            # Determine category
            category, reasons = determine_category(text, filename, bib_entry)
            
            # Clean filename
            new_filename = clean_filename(title)
            
            all_papers.append({
                "original_folder": original_folder,
                "original_filename": filename,
                "title": title,
                "new_filename": new_filename,
                "category": category,
                "reasons": reasons,
                "text_snippet": text[:1000]
            })
            
            # Add bib entry to category
            if bib_entry:
                category_bibs[category].append(bib_entry)
            
            # Copy to target folder
            dest_folder = os.path.join(base_dir, category)
            dest_path = os.path.join(dest_folder, new_filename)
            # Avoid overwriting
            counter = 1
            original_new_filename = new_filename
            while os.path.exists(dest_path):
                name_part, ext_part = os.path.splitext(original_new_filename)
                new_filename = f"{name_part}_{counter}{ext_part}"
                dest_path = os.path.join(dest_folder, new_filename)
                counter += 1
            all_papers[-1]["new_filename"] = new_filename
            shutil.copy2(pdf_path, dest_path)
            print(f"  → {category}/{new_filename}")

    # Write classification record
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
    for category in ["半监督", "监督", "自监督"]:
        bib_path = os.path.join(base_dir, category, f"{category}bib.txt")
        with open(bib_path, 'w', encoding='utf-8') as f:
            for entry in category_bibs.get(category, []):
                f.write(entry)
                f.write("\n\n")

    print("Processing complete!")

if __name__ == "__main__":
    main()
